# SPDX-License-Identifier: BSD-3-Clause
"""导出编排：konte.json（决定稿） → 参考图 + ScenePlan + A4·5-cut PDF + manifest。

产物目录结构（对齐《工程交接技术规格》§5.3 打包）：
  <out>/
    scenes/<SCENE>_<CUT>.ref.png        # 渲染参考层（锁定）
    scenes/<SCENE>_<CUT>.sceneplan.json # 生成 .tnz 的输入契约（供 C++ 内核）
    references/<SCENE>_<CUT>.png        # 成形参考图（交付给原画）
    storyboard.pdf                      # A4·5-cut 分镜
    manifest.json                       # 产物清单
    BUILD_REPORT.json                   # 本次导出摘要（PoC 用）
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

from PIL import Image, ImageDraw

from . import manifest as manifest_mod
from . import pdfgen, render, scene_plan, textfit
from .model import KonteProject
from .template import Template, coerce_template


def _placeholder(w: int, h: int, label: str) -> Image.Image:
    im = Image.new("RGB", (w, h), (205, 205, 205))
    d = ImageDraw.Draw(im)
    d.rectangle([4, 4, w - 5, h - 5], outline=(90, 90, 90), width=4)
    f = textfit.get_font(max(20, h // 12), bold=True)
    try:
        d.text((w / 2, h / 2), f"缺画面\n{label}", font=f, fill=(70, 70, 70), anchor="mm")
    except Exception:
        d.text((20, 20), f"MISSING {label}", font=f, fill=(70, 70, 70))
    return im


def _load_panel(project: KonteProject, cut: dict) -> Image.Image:
    fw = int(project.project["frame"]["width"])
    fh = int(project.project["frame"]["height"])
    try:
        p = project.resolve_level(cut)
        return render.load_panel(p)
    except FileNotFoundError:
        return _placeholder(fw, fh, cut.get("cut", cut["id"]))


def _load_panel_drawing(project: KonteProject, cut: dict, drawing: dict) -> Image.Image:
    fw = int(project.project["frame"]["width"])
    fh = int(project.project["frame"]["height"])
    try:
        p = project.resolve_drawing(cut, drawing)
        return render.load_panel(p)
    except FileNotFoundError:
        return _placeholder(fw, fh, cut.get("cut", cut["id"]))


def _audio_source(project: KonteProject, cut: dict):
    audio = cut.get("audio")
    if not audio or not audio.get("path"):
        return None
    p = Path(audio["path"])
    return p if p.is_absolute() else (project.base_dir / p)


def export_project(
    project_path: str | Path,
    out_dir: str | Path,
    *,
    base_psd: str | Path | None = None,
    schema_path: str | Path | None = None,
    targets: dict | None = None,
    pdf_template: "Template | dict | str | Path | None" = None,
    include_audio: bool = True,
) -> dict:
    targets = {"scenes": True, "pdf": True, "package": True, **(targets or {})}
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

    fw = int(project.project["frame"]["width"])
    fh = int(project.project["frame"]["height"])
    items: list[dict] = []
    project_id = project.data.get("project", {}).get("title", "project")

    for cut in project.sorted_cuts():
        fname = scene_plan.scene_filename(project, cut)
        stem = fname.replace(".tnz", "")
        # 参考图：一个 cut 的每张画面各渲染一张；单画面沿用 <stem>.ref.png，
        # 多画面用 <stem>.ref.01.png... → 由内核写成同一 .tnz 的 1..M 帧参考层。
        drawings = cut.get("drawings", [])
        multi = len(drawings) > 1
        ref_rels: list[str] = []
        for di, drawing in enumerate(drawings):
            panel = _load_panel_drawing(project, cut, drawing)
            ref_img = render.render_reference(panel, fw, fh)
            name = (f"{stem}.ref.png" if not multi else f"{stem}.ref.{di + 1:02d}.png")
            ref_path = scenes_dir / name
            if ref_path.exists():
                os.chmod(ref_path, stat.S_IWRITE | stat.S_IREAD)
            ref_img.save(ref_path, "PNG")
            if di == 0:
                shutil.copyfile(ref_path, refs_dir / f"{stem}.png")
            ref_rels.append(f"scenes/{name}")
        # ScenePlan
        plan = scene_plan.build_scene_plan(project, cut, include_audio=include_audio,
                                           reference_images=ref_rels)
        (scenes_dir / f"{stem}.sceneplan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        a_src = _audio_source(project, cut)
        a_info = scene_plan.audio_info(a_src) if include_audio else {}
        items.append({
            "cutId": cut["id"],
            "scene": cut.get("scene"),
            "cut": cut.get("cut"),
            "order": cut.get("order"),
            "sceneFile": f"scenes/{fname}",
            "referenceImage": f"references/{stem}.png",
            "totalFrames": project.total_frames(cut),
            "durationSec": project.duration_sec(cut),
            "page": project.page_of(cut),
            "hasAudio": bool(a_src and include_audio),
            "audioFile": (f"scenes/{Path(a_src).name}" if (a_src and include_audio) else None),
            "audioDurationSec": a_info.get("durationSec"),
        })

    pdf_rel = None
    pages = []
    if targets.get("pdf", True):
        pdf_path = out / "storyboard.pdf"
        effective_base = base_psd if base_psd is not None else tpl.base_psd
        pages = pdfgen.build_storyboard_pdf(project, pdf_path, effective_base, template=tpl)
        pdf_rel = "storyboard.pdf"

    man = manifest_mod.build_manifest(
        project_id=project_id,
        fps=project.fps,
        template=project.data["project"].get("template"),
        items=items,
        sequences=project.data.get("sequences", []),
        pdf=pdf_rel,
        package_dir=str(out) if targets.get("package", True) else None,
        include_audio=include_audio,
    )
    (out / "manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = {
        "projectId": project_id,
        "status": project.status,
        "fps": project.fps,
        "cutCount": len(items),
        "pageCount": len(pages),
        "pages": pages,
        "totalFrames": sum(i["totalFrames"] for i in items),
        "pdf": pdf_rel,
        "pdfTemplate": {"id": tpl.id, "name": tpl.name, "version": tpl.version,
                        "perPage": tpl.per_page, "canvas": list(tpl.canvas)},
        "outDir": str(out),
        "note": ".tnz 由 OpenToonz C++ 导出内核依据 scenes/*.sceneplan.json 生成（PoC 未含 OT 运行时）。",
    }
    (out / "BUILD_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
