# SPDX-License-Identifier: BSD-3-Clause
"""渲染页面预览 PNG + 校验 PDF（开发自检用）。

用法：
  python tools/preview_pages.py [konte.json] [base.psd|-] [pdf-template.json|template-id]
传 "-" 表示强制用内置网格（不加载 PSD）；不传 pdf-template 用默认模板。
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from konte_poc.model import KonteProject  # noqa: E402
from konte_poc import pdfgen, template  # noqa: E402


def main():
    proj = sys.argv[1] if len(sys.argv) > 1 else "examples/EP01/konte.json"
    psd_arg = sys.argv[2] if len(sys.argv) > 2 else r"X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"
    psd = "" if psd_arg == "-" else psd_arg
    tpl_arg = sys.argv[3] if len(sys.argv) > 3 else None
    outdir = Path(r"X:\agent\NARRATIVISM_otz\_refs")
    p = KonteProject.load(proj)
    tpl = template.coerce_template(tpl_arg)
    imgs, infos = pdfgen.compose_pages(p, psd, template=tpl)
    stem = "storyboard"
    if tpl.id != "scfilms_storyboard":
        suffix = tpl.id[len("scfilms_storyboard"):].strip("_") if tpl.id.startswith("scfilms_storyboard") else tpl.id
        stem = "storyboard_" + suffix
    for i, im in enumerate(imgs, 1):
        prev = im.copy()
        prev.thumbnail((1240, 1754))
        prev.save(outdir / f"{stem}_p{i}.png")
    print("template", tpl.id, "pages", len(imgs), "size", imgs[0].size)
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
