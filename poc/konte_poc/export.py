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
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from . import manifest as manifest_mod
from . import pdfgen, render, scene_plan, textfit
from .model import KonteProject


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


def export_project(
    project_path: str | Path,
    out_dir: str | Path,
    *,
    base_psd: str | Path | None = None,
    schema_path: str | Path | None = None,
    targets: dict | None = None,
) -> dict:
    targets = {"scenes": True, "pdf": True, "package": True, **(targets or {})}
    project = KonteProject.load(project_path, schema_path=schema_path)
    project.check_export_gate()

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
        panel = _load_panel(project, cut)
        # 渲染参考层（全分辨率）
        ref_img = render.render_reference(panel, fw, fh)
        ref_path = scenes_dir / f"{stem}.ref.png"
        ref_img.save(ref_path, "PNG")
        # 成形参考图（交付）
        shutil.copyfile(ref_path, refs_dir / f"{stem}.png")
        # ScenePlan
        plan = scene_plan.build_scene_plan(project, cut)
        (scenes_dir / f"{stem}.sceneplan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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
        })

    pdf_rel = None
    pages = []
    if targets.get("pdf", True):
        pdf_path = out / "storyboard.pdf"
        pages = pdfgen.build_storyboard_pdf(project, pdf_path, base_psd)
        pdf_rel = "storyboard.pdf"

    man = manifest_mod.build_manifest(
        project_id=project_id,
        fps=project.fps,
        template=project.data["project"].get("template"),
        items=items,
        sequences=project.data.get("sequences", []),
        pdf=pdf_rel,
        package_dir=str(out) if targets.get("package", True) else None,
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
        "outDir": str(out),
        "note": ".tnz 由 OpenToonz C++ 导出内核依据 scenes/*.sceneplan.json 生成（PoC 未含 OT 运行时）。",
    }
    (out / "BUILD_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
