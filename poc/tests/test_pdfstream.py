# SPDX-License-Identifier: BSD-3-Clause
"""P5 强化：流式 / 分卷 PDF 单测（内存友好，逐页 Flate）。"""
import sys
import tempfile
import unittest
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

from PIL import Image  # noqa: E402

from konte_poc import pdfgen, template as tplmod  # noqa: E402
from konte_poc.pdfstream import write_pdf_streaming  # noqa: E402
from _fixtures import make_project  # noqa: E402

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


def tiny_template() -> tplmod.Template:
    data = {
        "id": "tiny", "name": "tiny", "version": "1.0.0",
        "canvas": {"width": 400, "height": 560, "dpi": 72},
        "perPage": 3,
        "columns": {
            "cut": {"x0": 10, "x1": 40}, "picture": {"x0": 40, "x1": 200},
            "action": {"x0": 200, "x1": 280}, "dialogue": {"x0": 280, "x1": 360},
            "music": {"x0": 360, "x1": 380}, "duration": {"x0": 380, "x1": 400},
        },
        "frame": {
            "outer": {"x0": 2, "y0": 2, "x1": 398, "y1": 558, "borderWidth": 1},
            "inner": {"x0": 5, "y0": 5, "x1": 395, "y1": 555},
            "verticalLineWidth": 1, "horizontalLineWidth": 1, "heavyLineWidth": 2,
            "heavyYs": [10, 555],
        },
        "rows": {"header": {"y0": 10, "y1": 20},
                 "cuts": [{"y0": 20, "y1": 200}, {"y0": 200, "y1": 380}, {"y0": 380, "y1": 555}]},
        "decorations": {
            "noLabel": {"text": "No.", "x": 5, "y": 0, "size": 6, "font": "decor"},
            "noLine": {"x0": 20, "y0": 8, "x1": 60, "y1": 8, "width": 1},
            "pageNo": {"x": 10, "y": 0, "font": "pageNo"},
            "pageTotalHint": {"text": "( + )", "x": 350, "y": 556, "size": 6, "font": "decor"},
            "pageTotalBox": {"x0": 340, "y0": 545, "x1": 395, "y1": 558},
            "headerLabels": [{"text": "CUT", "x": 12, "y": 12, "font": "header"}],
        },
        "picture": {"inset": 2, "mode": "contain", "oversizeMode": "cover",
                    "bleedIndicator": False, "whiteFill": True},
        "fonts": {
            "default": {"family": "Source Han Sans", "size": 9, "lineSpacing": 1.1,
                        "overflow": "shrink", "minSize": 5},
            "header": {"family": "Source Han Sans", "size": 6},
            "cut": {"family": "Source Han Sans", "size": 9, "bold": True},
            "action": {"family": "Source Han Sans", "size": 9},
            "dialogue": {"family": "Source Han Sans", "size": 9},
            "music": {"family": "Source Han Sans", "size": 8},
            "duration": {"family": "Source Han Sans", "size": 9},
            "pageNo": {"family": "Source Han Sans", "size": 10},
            "pageTotal": {"family": "Source Han Sans", "size": 8},
            "decor": {"family": "Source Han Sans", "size": 8},
        },
        "text": {"pad": 2, "align": "left", "valign": "top", "kinsoku": True, "minSize": 4},
    }
    return tplmod.from_dict(data)


@unittest.skipIf(PdfReader is None, "pypdf 未安装")
class TestPdfStreaming(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="konte_pdf_"))

    def test_write_streaming_synthetic(self):
        imgs = [Image.new("RGB", (200, 100), (30 * i, 60, 90)) for i in range(5)]
        out = self.tmp / "s.pdf"
        info = write_pdf_streaming(imgs, out, dpi=100)
        self.assertEqual(info["pages"], 5)
        r = PdfReader(str(out))
        self.assertEqual(len(r.pages), 5)
        b = r.pages[0].mediabox
        self.assertAlmostEqual(float(b.width), 144.0, places=1)
        self.assertAlmostEqual(float(b.height), 72.0, places=1)

    def _proj(self, n):
        import json
        d = make_project(n)
        d["project"]["frame"] = {"width": 320, "height": 180, "aspect": "16:9"}
        # 所有 cut 指向同一张已存在的画面，避免依赖占位图逻辑
        panel_dir = self.tmp / "panels"
        panel_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), (210, 220, 230)).save(panel_dir / "p.png", "PNG")
        for c in d["cuts"]:
            c["drawings"][0]["level"] = "panels/p.png"
        p = self.tmp / "konte.json"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return p

    def test_build_streaming_auto(self):
        from konte_poc.model import KonteProject
        proj = KonteProject.load(self._proj(30))  # 30/3 = 10 页 > 8 → 流式
        tpl = tiny_template()
        out = self.tmp / "storyboard.pdf"
        infos = pdfgen.build_storyboard_pdf(proj, out, base_psd="", template=tpl)
        self.assertEqual(len(infos), 10)
        r = PdfReader(str(out))
        self.assertEqual(len(r.pages), 10)
        b = r.pages[0].mediabox
        self.assertAlmostEqual(float(b.width), 400.0, places=1)

    def test_build_split(self):
        from konte_poc.model import KonteProject
        proj = KonteProject.load(self._proj(30))
        tpl = tiny_template()
        res = pdfgen.build_storyboard_pdfs_split(proj, self.tmp / "parts", base_psd="",
                                                 template=tpl, pages_per_file=4)
        self.assertEqual(len(res["files"]), 3)  # 4+4+2
        total = 0
        for f in res["files"]:
            total += len(PdfReader(f).pages)
        self.assertEqual(total, 10)
        self.assertEqual(len(res["pageInfos"]), 10)


if __name__ == "__main__":
    unittest.main()
