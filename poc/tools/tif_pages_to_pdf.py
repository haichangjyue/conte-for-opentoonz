# SPDX-License-Identifier: BSD-3-Clause
"""把已有的 Photoshop 完稿分镜页（TIF/PNG）按 A4 300dpi 合成多页 PDF。

用途：真实社内分镜很多是 PS 完稿导出的整页 TIFF（不是 konte.json）。本工具把这类页面
**保真**转成可打印的 A4 PDF（像素尺寸即 A4@300dpi：2480×3507），用于交付/校对。
（这不是"重新排版"：页面内容原样保留；需要结构化重排请走 konte.json 导出。）

用法：
  python tools/tif_pages_to_pdf.py out.pdf page1.tif page2.tif ...
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from konte_poc.pdfstream import write_pdf_streaming  # noqa: E402

A4_W_PX, A4_H_PX = 2480, 3507
A4_DPI = 300


def _load_page(p: Path) -> Image.Image:
    im = Image.open(p)
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    rgb = im.convert("RGB")
    if rgb.size != (A4_W_PX, A4_H_PX):
        # 保持内容比例，等比缩放到 A4 画布（白底居中）
        canvas = Image.new("RGB", (A4_W_PX, A4_H_PX), (255, 255, 255))
        r = rgb.copy()
        r.thumbnail((A4_W_PX, A4_H_PX))
        canvas.paste(r, ((A4_W_PX - r.width) // 2, (A4_H_PX - r.height) // 2))
        rgb = canvas
    return rgb


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("用法: python tools/tif_pages_to_pdf.py out.pdf page1.tif [page2.tif ...]", file=sys.stderr)
        return 2
    out = Path(argv[1])
    pages = [Path(x) for x in argv[2:]]
    for p in pages:
        if not p.exists():
            print(f"缺少文件: {p}", file=sys.stderr)
            return 2

    def gen():
        for p in pages:
            yield _load_page(p)

    info = write_pdf_streaming(gen(), out, dpi=A4_DPI)
    print(f"[ok] {out}  pages={info['pages']}  {info['widthPt']}x{info['heightPt']}pt  {info['bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
