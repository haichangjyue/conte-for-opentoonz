# SPDX-License-Identifier: BSD-3-Clause
"""渲染页面预览 PNG + 校验 PDF（开发自检用）。"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from konte_poc.model import KonteProject  # noqa: E402
from konte_poc import pdfgen  # noqa: E402


def main():
    proj = sys.argv[1] if len(sys.argv) > 1 else "examples/EP01/konte.json"
    psd = sys.argv[2] if len(sys.argv) > 2 else r"X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"
    outdir = Path(r"X:\agent\NARRATIVISM_otz\_refs")
    p = KonteProject.load(proj)
    imgs, infos = pdfgen.compose_pages(p, psd)
    for i, im in enumerate(imgs, 1):
        prev = im.copy()
        prev.thumbnail((1240, 1754))
        prev.save(outdir / f"storyboard_p{i}.png")
    print("pages", len(imgs), "size", imgs[0].size)
    try:
        from pypdf import PdfReader
        pdf = "examples/EP01/out/storyboard.pdf"
        r = PdfReader(pdf)
        b = r.pages[0].mediabox
        print("pdf pages", len(r.pages))
        print("mediabox mm", round(float(b.width) * 25.4 / 72, 2), "x", round(float(b.height) * 25.4 / 72, 2))
        print("pdf bytes", os.path.getsize(pdf))
    except Exception as e:
        print("pypdf skip", e)


if __name__ == "__main__":
    main()
