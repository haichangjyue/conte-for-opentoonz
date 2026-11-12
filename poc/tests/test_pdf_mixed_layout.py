# SPDX-License-Identifier: BSD-3-Clause
"""PDF 混合布局回归：普通镜头 + 跨格(layout)镜头共存时不应崩溃，且分页合理。

回归的是 `_iter_layout_pages` 在「部分 cut 有 layout、部分没有」时的 KeyError 崩溃。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_POC))

from konte_poc.export import export_project  # noqa: E402


class MixedLayoutPdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "EP01"
        src = _POC / "examples" / "EP01"
        if not (src / "konte.json").exists():
            self.skipTest("缺少 EP01 示例")
        shutil.copytree(src, self.dir)
        self.project = self.dir / "konte.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _add_layout_cut(self, row_span=3, page=1):
        data = json.loads(self.project.read_text(encoding="utf-8"))
        fps = int(data["project"]["fps"])
        n = max(c["number"] for c in data["cuts"]) + 1
        label = f"C{n:03d}"
        cut = {
            "id": f"ep01-c{n:03d}", "sequenceId": "seq1", "scene": "EP01", "cut": label,
            "number": n, "order": max(c["order"] for c in data["cuts"]) + 1,
            "layout": {"page": page, "rowStart": 0, "rowSpan": row_span},
            "duration": {"status": "fixed", "seconds": 1, "frames": 0, "totalFrames": fps},
            "frame": {"kind": "standard", "rect": {"x": 0, "y": 0, "w": 1920, "h": 1080}},
            "drawings": [
                {"id": f"{label}-d{i+1}", "role": "panel",
                 "level": f"panels/C00{i+1}.png", "source": "desktop",
                 "deviceId": "t", "revision": 1, "updatedAt": "2026-11-12T14:29:05+08:00"}
                for i in range(row_span)
            ],
            "action": "跨格镜头", "dialogue": [], "musicSe": [], "audio": None,
            "camera": {"note": "", "keyframes": []}, "state": "final", "lock": None,
            "export": {"status": "notExported", "sceneFile": None},
            "revision": 1, "updatedAt": "2026-11-12T14:29:05+08:00",
        }
        data["cuts"].append(cut)
        self.project.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return label

    def test_multicell_keeps_black_grid_and_inset(self):
        """多格镜头：画面应嵌在黑色格线内，行间黑色分隔线不能被白色画面覆盖。"""
        from konte_poc import pdfgen
        from konte_poc.model import KonteProject
        from konte_poc.template import coerce_template

        data = json.loads(self.project.read_text(encoding="utf-8"))
        base_cut = data["cuts"][0]
        cut = dict(base_cut)
        cut["id"] = "x-c001"
        cut["cut"] = "C001"
        cut["number"] = 1
        cut["order"] = 1
        cut["layout"] = {"page": 1, "rowStart": 0, "rowSpan": 2}
        cut["drawings"] = [data["cuts"][0]["drawings"][0], data["cuts"][1]["drawings"][0]]
        data["cuts"] = [cut]
        data["project"]["status"] = "final"
        p2 = Path(self.tmp.name) / "multi.json"
        p2.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        tpl = coerce_template(None)
        base = tpl.data.get("basePsd")
        if not base or not Path(base).exists():
            self.skipTest("缺少底版 PSD")
        imgs, _ = pdfgen.compose_pages(KonteProject.load(p2), base,
                                       per_page=tpl.per_page, template=tpl)
        img = imgs[0].convert("RGB")
        rows = tpl.rows
        xb = (tpl.columns["picture"].x0 + tpl.columns["picture"].x1) // 2
        # 第 1、2 行边界处应为黑色格线（未被白色画面覆盖）
        for y in (rows[0].y1, rows[1].y0):
            vals = [img.getpixel((xb, y + d)) for d in (-4, 0, 4, 6)]
            darkest = min(sum(v) / 3 for v in vals)
            self.assertLess(darkest, 120, f"行边界 y={y} 的黑色格线被覆盖了")

    def test_mixed_layout_exports_without_crash(self):
        self._add_layout_cut(row_span=3, page=1)  # 故意用 page1 rowStart0 与已有 cut 冲突
        out = Path(self.tmp.name) / "out"
        export_project(self.project, out, targets={"scenes": False, "package": False})
        pdf = out / "storyboard.pdf"
        self.assertTrue(pdf.exists(), "应生成 storyboard.pdf")
        self.assertGreater(pdf.stat().st_size, 1000)
        try:
            from pypdf import PdfReader
            n = len(PdfReader(str(pdf)).pages)
            self.assertGreaterEqual(n, 2, "7 普通镜头 + 1 跨格镜头应 >= 2 页")
        except ImportError:
            pass


if __name__ == "__main__":
    unittest.main()
