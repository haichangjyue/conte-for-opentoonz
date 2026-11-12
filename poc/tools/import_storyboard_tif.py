# SPDX-License-Identifier: BSD-3-Clause
"""把真实完稿分镜页（PS 导出的整页 TIF/PNG）反解成 konte.json（支持一个镜头跨多格）。

真实社内分镜常用「一页 5 行、一个镜头按需占 1..N 格」的排布（用于展开表演/多张画面）。
本工具：
  * 读取整页图像，用模板网格定位每页 CUT 列里的镜号文字 → 推断每个镜头的 rowStart/rowSpan；
  * 按行裁出 PICTURE 列画面 → panels/*.png（一个镜头跨 N 行 = N 张画面）；
  * 可选 sidecar JSON 提供每个镜头的 action/dialogue/musicSe/时长（缺省 2s）；
  * 生成符合 konte.schema.json 的 konte.json（带 cut.layout），可直接走现有导出。

用法：
  python tools/import_storyboard_tif.py --out examples/SK01 --pages 01.tif 02.tif \
     [--sidecar examples/SK01/tif_texts.json] [--fps 24] [--title SK01]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
POC = HERE.parent
sys.path.insert(0, str(POC))

from konte_poc import template as tplmod  # noqa: E402


def _iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def detect_cut_rows(gray: np.ndarray, tpl) -> list[int]:
    """在 CUT 列检测镜号文字块，返回每个镜头起始行索引（0 基）。"""
    col = tpl.columns["cut"]
    x0, x1 = col.x0 + 5, col.x1 - 5
    y_top = tpl.header.y1
    y_bot = tpl.rows[-1].y1
    seg = gray[y_top:y_bot, x0:x1]
    ink = (seg < 110).sum(axis=1) > 3
    idx = np.where(ink)[0]
    groups = []
    for i in idx:
        if groups and i - groups[-1][-1] <= 8:
            groups[-1].append(i)
        else:
            groups.append([i])
    starts = []
    row_tops = [r.y0 for r in tpl.rows]
    for g in groups:
        if len(g) < 20:  # 排除细线/噪点
            continue
        y = y_top + int(np.mean(g))
        # 映射到最近的行走廊顶部
        best = min(range(len(row_tops)), key=lambda k: abs(row_tops[k] - y))
        if abs(row_tops[best] - y) <= 90 and best not in starts:
            starts.append(best)
    if not starts:
        # 兜底：假定每行一个镜头
        starts = list(range(len(tpl.rows)))
    return sorted(starts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="import_storyboard_tif")
    ap.add_argument("--pages", nargs="+", required=True, help="整页 TIF/PNG（按页顺序）")
    ap.add_argument("--out", required=True, help="输出工程目录")
    ap.add_argument("--sidecar", default=None, help="每镜头文字/时长 JSON（按页面顺序的数组）")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--title", default="SK01")
    ap.add_argument("--scene", default="SK01")
    ap.add_argument("--template", default=None, help="PDF 版式模板 JSON（默认 scfilms）")
    args = ap.parse_args(argv)

    tpl = tplmod.coerce_template(args.template)
    out = Path(args.out)
    panels_dir = out / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    side = []
    if args.sidecar and Path(args.sidecar).exists():
        side = json.loads(Path(args.sidecar).read_text(encoding="utf-8"))

    cuts = []
    n = 0
    now = _iso()
    for pi, page_path in enumerate(args.pages, start=1):
        p = Path(page_path)
        im = Image.open(p)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        rgb = im.convert("RGB")
        gray = np.array(im.convert("L"))
        starts = detect_cut_rows(gray, tpl)
        rows = tpl.rows
        pic = tpl.columns["picture"]
        for si, r0 in enumerate(starts):
            r1 = starts[si + 1] - 1 if si + 1 < len(starts) else len(rows) - 1
            r1 = min(r1, len(rows) - 1)
            span = r1 - r0 + 1
            n += 1
            meta = side[n - 1] if n - 1 < len(side) else {}
            cut_name = str(meta.get("cut", n))
            drawings = []
            for k, ridx in enumerate(range(r0, r1 + 1)):
                row = rows[ridx]
                box = (pic.x0 + 6, row.y0 + 6, pic.x1 - 6, row.y1 - 6)
                panel = rgb.crop(box)
                fname = f"p{pi:02d}_c{n:03d}_r{k + 1}.png"
                panel.save(panels_dir / fname, "PNG")
                drawings.append({
                    "id": f"p{pi:02d}c{n:03d}-d{k + 1}",
                    "role": "panel",
                    "level": f"panels/{fname}",
                    "source": "desktop",
                    "deviceId": None,
                    "revision": 1,
                    "updatedAt": now,
                })
            sec = int(meta.get("seconds", 2))
            frm = int(meta.get("frames", 0))
            cuts.append({
                "id": f"{args.scene.lower()}-c{n:03d}",
                "sequenceId": "seq1",
                "scene": args.scene,
                "cut": cut_name,
                "number": n,
                "order": n,
                "page": pi,
                "layout": {"page": pi, "rowStart": r0, "rowSpan": span},
                "duration": {"status": "fixed", "seconds": sec, "frames": frm,
                             "totalFrames": sec * args.fps + frm},
                "frame": {"kind": "standard", "rect": {"x": 0, "y": 0, "w": 1920, "h": 1080}},
                "drawings": drawings,
                "action": meta.get("action", ""),
                "dialogue": meta.get("dialogue", []),
                "musicSe": meta.get("musicSe", []),
                "camera": {"note": "", "keyframes": []},
                "state": "final",
                "lock": None,
                "export": {"status": "notExported", "sceneFile": None},
                "revision": 1,
                "updatedAt": now,
            })

    project = {
        "schemaVersion": "1.0",
        "project": {
            "title": args.title, "status": "final", "fps": args.fps,
            "template": "scfilms_StoryBoard.psd", "pdfTemplate": "scfilms_storyboard",
            "frame": {"width": 1920, "height": 1080, "aspect": "16:9"},
            "bleed": {"left": 0, "right": 0, "top": 0, "bottom": 0},
            "cameraBox": {"x": 0, "y": 0, "w": 1920, "h": 1080},
        },
        "exportConfig": {"mode": "renderedRef", "granularity": "perCut",
                         "namingPattern": "{scene}_{cut}.tnz",
                         "onTbdDuration": "blockUntilResolved", "defaultTbdFrames": 24},
        "sequences": [{"id": "seq1", "title": "A"}],
        "cuts": cuts,
        "meta": {"createdAt": now, "updatedAt": now, "authors": ["import"]},
    }
    (out / "konte.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] {out/'konte.json'}  pages={len(args.pages)} cuts={len(cuts)}")
    for c in cuts:
        print(f"  cut {c['cut']}: page {c['page']} rows {c['layout']['rowStart']}.."
              f"{c['layout']['rowStart'] + c['layout']['rowSpan'] - 1} span {c['layout']['rowSpan']} "
              f"dur {c['duration']['seconds']}+{c['duration']['frames']:02d} drawings {len(c['drawings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
