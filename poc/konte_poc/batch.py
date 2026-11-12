# SPDX-License-Identifier: BSD-3-Clause
"""P5 批量导出编排：断点续 + 进度/日志 + 失败汇总（支持 >200 cut）。

与一次性 `export_project` 的区别：
  * 逐个 cut 处理，进度事件写入 JSONL（`export_log.jsonl`）并可回调；
  * 状态文件 `_export_state.json` 记录每个 cut 的画面哈希 / ScenePlan 哈希，
    重跑时跳过未变化的参考图与 ScenePlan，并跳过已生成的 `.tnz`（断点续）；
  * 可选调用 OpenToonz 导出内核（`konte-export`）批量生成真实 `.tnz`；无内核时产出结构包；
  * 单 cut 失败不影响其余 cut，最终 `batch_report.json` 汇总 failed 列表；
  * PDF 可开关（>200 cut 的 50+ 页 A4 建议配合 --no-pdf 或分卷，避免内存峰值）。

用法（CLI）：`python -m konte_poc batch <konte.json> --out <dir> [--exporter ...] [--no-pdf]`
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

from . import manifest as manifest_mod
from . import pdfgen, render, scene_plan
from .model import KonteProject
from .template import coerce_template

STATE_NAME = "_export_state.json"
LOG_NAME = "export_log.jsonl"
REPORT_NAME = "batch_report.json"


def _sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _file_hash(p: Path) -> str:
    try:
        return _sha1_bytes(p.read_bytes())
    except OSError:
        return "MISSING"


def _json_hash(obj: dict) -> str:
    return _sha1_bytes(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "cuts": {}}


def _save_state(path: Path, state: dict) -> None:
    state["updatedAt"] = _now()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class _Progress:
    """JSONL 日志 + 可选回调 + 控制台进度。"""

    def __init__(self, log_path: Path, callback=None, quiet=False):
        self.log_path = log_path
        self.callback = callback
        self.quiet = quiet
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.log_path, "a", encoding="utf-8")

    def emit(self, **rec):
        rec = {"ts": _now(), **rec}
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fh.flush()
        if self.callback:
            try:
                self.callback(rec)
            except Exception:
                pass
        if not self.quiet and not self.callback:
            i, n = rec.get("index"), rec.get("total")
            head = f"[{i}/{n}]" if i and n else "[batch]"
            msg = rec.get("message") or ""
            print(f"{head} {rec.get('cutId','-')} {rec.get('status','')} {msg}".rstrip(), flush=True)

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass


def _exporter_cmd(exporter: str | Path) -> list[str]:
    e = str(exporter)
    suffix = Path(e).suffix.lower()
    if suffix == ".py":
        return [sys.executable, e]
    if suffix == ".ps1":
        return ["powershell", "-ExecutionPolicy", "Bypass", "-File", e]
    return [e]


def _run_exporter(exporter: str | Path, scenes_dir: Path, pending_stems: set[str],
                  tnz_template: str | Path | None, progress: _Progress) -> dict:
    """只让内核处理 pending 的 ScenePlan：临时移走其余 plan，跑完还原。"""
    hold = scenes_dir / "_hold_plans"
    if hold.exists():
        shutil.rmtree(hold, ignore_errors=True)
    hold.mkdir(parents=True)
    moved: list[Path] = []
    for p in scenes_dir.glob("*.sceneplan.json"):
        if p.name[: -len(".sceneplan.json")] not in pending_stems:
            dst = hold / p.name
            shutil.move(str(p), str(dst))
            moved.append(p)

    cmd = _exporter_cmd(exporter) + ["--sceneplans", str(scenes_dir), "--out", str(scenes_dir)]
    if tnz_template:
        cmd += ["--template", str(tnz_template)]
    env = os.environ.copy()
    try:
        from .package import _exporter_env
        env = _exporter_env(exporter)
    except Exception:
        pass

    progress.emit(event="exporter.start", count=len(pending_stems), cmd=cmd)
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    dt = round(time.time() - t0, 2)
    progress.emit(event="exporter.end", returncode=proc.returncode, elapsedSec=dt,
                  stdoutTail=(proc.stdout or "")[-2000:], stderrTail=(proc.stderr or "")[-2000:])
    # 还原被移走的 plan
    for p in moved:
        try:
            shutil.move(str(hold / p.name), str(p))
        except Exception:
            pass
    shutil.rmtree(hold, ignore_errors=True)
    # 清理内核构建产物
    for junk in ("export_report.json",):
        jp = scenes_dir / junk
        if jp.exists():
            jp.unlink()
    icons = scenes_dir / "sceneIcons"
    if icons.exists():
        shutil.rmtree(icons, ignore_errors=True)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
            "elapsedSec": dt}


def export_batch(
    project_path: str | Path,
    out_dir: str | Path,
    *,
    base_psd: str | Path | None = None,
    schema_path: str | Path | None = None,
    pdf_template=None,
    exporter: str | Path | None = None,
    tnz_template: str | Path | None = None,
    resume: bool = True,
    include_audio: bool = True,
    make_pdf: bool = True,
    force_pdf: bool = False,
    pdf_split_pages: int | None = None,
    quiet: bool = False,
    progress_callback=None,
) -> dict:
    t_start = time.time()
    project = KonteProject.load(project_path, schema_path=schema_path)
    project.check_export_gate()
    tpl_src = pdf_template
    if tpl_src is None:
        tpl_src = project.data.get("project", {}).get("pdfTemplate")
    tpl = coerce_template(tpl_src)

    out = Path(out_dir)
    scenes_dir = out / "scenes"
    refs_dir = out / "references"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    refs_dir.mkdir(parents=True, exist_ok=True)

    state_path = out / STATE_NAME
    state = _load_state(state_path) if resume else {"version": 1, "cuts": {}}
    state.setdefault("cuts", {})
    progress = _Progress(out / LOG_NAME, callback=progress_callback, quiet=quiet)

    cuts = project.sorted_cuts()
    total = len(cuts)
    fw = int(project.project["frame"]["width"])
    fh = int(project.project["frame"]["height"])
    project_id = project.data.get("project", {}).get("title", "project")

    items: list[dict] = []
    rendered = reused_refs = plan_written = plan_reused = 0
    failed: list[dict] = []
    pending: list[dict] = []
    tnz_reused = 0

    progress.emit(event="batch.start", projectId=project_id, total=total,
                  resume=resume, exporter=bool(exporter))

    for idx, cut in enumerate(cuts, start=1):
        cid = cut["id"]
        fname = scene_plan.scene_filename(project, cut)
        stem = fname.replace(".tnz", "")
        drawings = cut.get("drawings", [])
        multi = len(drawings) > 1
        ref_names = [(f"{stem}.ref.png" if not multi else f"{stem}.ref.{i + 1:02d}.png")
                     for i in range(len(drawings))]
        ref_paths = [scenes_dir / n for n in ref_names]
        ref_rels = [f"scenes/{n}" for n in ref_names]
        plan_path = scenes_dir / f"{stem}.sceneplan.json"
        tnz_path = scenes_dir / fname
        st = state["cuts"].get(cid, {})

        try:
            # ---- 画面哈希（该 cut 全部画面）----
            panel_hash = _sha1_bytes("|".join(
                _file_hash(project.resolve_drawing(cut, d)) for d in drawings).encode("utf-8"))

            # ---- 参考图（多画面 = 多帧参考层源图；画面未变则复用）----
            if resume and all(p.exists() for p in ref_paths) and st.get("panelHash") == panel_hash:
                reused_refs += 1
            else:
                for di, drawing in enumerate(drawings):
                    panel = _load_panel_drawing(project, cut, drawing)
                    ref_img = render.render_reference(panel, fw, fh)
                    rp = ref_paths[di]
                    if rp.exists():
                        os.chmod(rp, stat.S_IWRITE | stat.S_IREAD)
                    ref_img.save(rp, "PNG")
                rendered += 1
                progress.emit(event="ref", index=idx, total=total, cutId=cid, status="rendered")
            # 交付参考图补齐（取第一张）
            ref_dst = refs_dir / f"{stem}.png"
            if ref_paths and (not ref_dst.exists() or _file_hash(ref_dst) != _file_hash(ref_paths[0])):
                shutil.copyfile(ref_paths[0], ref_dst)

            # ---- ScenePlan（内容未变则复用）----
            plan = scene_plan.build_scene_plan(project, cut, include_audio=include_audio,
                                               reference_images=ref_rels)
            plan_hash = _json_hash(plan)
            if resume and plan_path.exists() and st.get("planHash") == plan_hash:
                plan_reused += 1
            else:
                plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
                plan_written += 1
                progress.emit(event="plan", index=idx, total=total, cutId=cid, status="written")

            # ---- 是否需要生成 .tnz ----
            tnz_ok = bool(resume and tnz_path.exists() and st.get("tnzPlanHash") == plan_hash)
            if tnz_ok:
                tnz_reused += 1
            elif exporter:
                pending.append({"cutId": cid, "stem": stem, "planPath": plan_path, "planHash": plan_hash})
            else:
                pass  # 无内核：结构包

            a_src = _audio_source(project, cut)
            a_info = scene_plan.audio_info(a_src) if include_audio else {}
            items.append({
                "cutId": cid, "scene": cut.get("scene"), "cut": cut.get("cut"),
                "order": cut.get("order"), "sceneFile": f"scenes/{fname}",
                "referenceImage": f"references/{stem}.png",
                "totalFrames": project.total_frames(cut), "durationSec": project.duration_sec(cut),
                "page": project.page_of(cut), "hasAudio": bool(a_src and include_audio),
                "audioFile": (f"scenes/{Path(a_src).name}" if (a_src and include_audio) else None),
                "audioDurationSec": a_info.get("durationSec"),
            })

            state["cuts"][cid] = {
                "panelHash": panel_hash, "planHash": plan_hash,
                "tnzPlanHash": plan_hash if tnz_ok else st.get("tnzPlanHash"),
                "sceneFile": f"scenes/{fname}", "updatedAt": _now(),
            }
            _save_state(state_path, state)
            progress.emit(event="cut", index=idx, total=total, cutId=cid, status="ok")
        except Exception as e:  # noqa: BLE001 - 单 cut 失败不阻塞整体
            failed.append({"cutId": cid, "error": f"{type(e).__name__}: {e}"})
            progress.emit(event="cut", index=idx, total=total, cutId=cid, status="failed",
                          message=str(e))

    # ---- 批量生成 .tnz ----
    tnz_generated = 0
    tnz_failed: list[dict] = []
    if exporter and pending:
        ex = _run_exporter(exporter, scenes_dir, {p["stem"] for p in pending}, tnz_template, progress)
        for p in pending:
            tnz = scenes_dir / (p["stem"] + ".tnz")
            if tnz.exists():
                st = state["cuts"].setdefault(p["cutId"], {})
                st["tnzPlanHash"] = p["planHash"]
                tnz_generated += 1
                progress.emit(event="tnz", cutId=p["cutId"], status="generated")
            else:
                tnz_failed.append({"cutId": p["cutId"], "error": f"exporter rc={ex['returncode']}"})
                progress.emit(event="tnz", cutId=p["cutId"], status="failed",
                              message=(ex.get("stderr") or "")[-300:])
        _save_state(state_path, state)
    failed.extend(tnz_failed)
    failed_ids = {f["cutId"] for f in failed}
    items_ok = [it for it in items if it["cutId"] not in failed_ids]

    # ---- PDF ----
    pdf_rel = None
    pdf_reused = False
    pdf_files: list[str] = []
    pages: list[dict] = []
    if make_pdf:
        pdf_path = out / "storyboard.pdf"
        unchanged = (rendered == 0 and plan_written == 0 and not force_pdf and pdf_path.exists()
                     and resume and not pending and not failed)
        if unchanged:
            pdf_reused = True
            progress.emit(event="pdf", status="reused", path=str(pdf_path))
        elif pdf_split_pages:
            effective_base = base_psd if base_psd is not None else tpl.base_psd
            res = pdfgen.build_storyboard_pdfs_split(
                project, out, effective_base, template=tpl, pages_per_file=pdf_split_pages)
            pages = res["pageInfos"]
            pdf_files = res["files"]
            pdf_rel = Path(pdf_files[0]).name if pdf_files else None
            progress.emit(event="pdf", status="split", files=len(pdf_files), pages=len(pages))
        else:
            effective_base = base_psd if base_psd is not None else tpl.base_psd
            pages = pdfgen.build_storyboard_pdf(project, pdf_path, effective_base, template=tpl)
            pdf_rel = "storyboard.pdf"
            progress.emit(event="pdf", status="generated", pages=len(pages))

    # ---- manifest ----
    man = manifest_mod.build_manifest(
        project_id=project_id, fps=project.fps,
        template=project.data["project"].get("template"), items=items,
        sequences=project.data.get("sequences", []), pdf=pdf_rel if not pdf_reused else "storyboard.pdf",
        package_dir=None, include_audio=include_audio,
    )
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = round(time.time() - t_start, 2)
    expected_pages = (total + tpl.per_page - 1) // tpl.per_page if total else 0
    report = {
        "projectId": project_id, "outDir": str(out), "cutCount": total,
        "pageCount": len(pages) if pages else expected_pages,
        "totalFrames": sum(i["totalFrames"] for i in items),
        "rendered": rendered, "reusedReference": reused_refs,
        "planWritten": plan_written, "planReused": plan_reused,
        "tnzGenerated": tnz_generated, "tnzReused": tnz_reused,
        "tnzPending": len(pending), "pdf": pdf_rel if not pdf_reused else "storyboard.pdf",
        "pdfReused": pdf_reused, "pdfFiles": pdf_files, "failed": failed,
        "ok": len(failed) == 0,
        "status": "ok" if not failed else ("partial" if items_ok else "failed"),
        "elapsedSec": elapsed, "logPath": str(out / LOG_NAME), "statePath": str(state_path),
    }
    (out / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    progress.emit(event="batch.end", ok=report["ok"], status=report["status"], elapsedSec=elapsed)
    progress.close()
    return report


# 复用 export 的占位图加载（避免重复实现）
def _load_panel(project: KonteProject, cut: dict):
    from .export import _load_panel as _lp
    return _lp(project, cut)


def _load_panel_drawing(project: KonteProject, cut: dict, drawing: dict):
    from .export import _load_panel_drawing as _lpd
    return _lpd(project, cut, drawing)


def _audio_source(project: KonteProject, cut: dict):
    audio = cut.get("audio")
    if not audio or not audio.get("path"):
        return None
    p = Path(audio["path"])
    return p if p.is_absolute() else (project.base_dir / p)
