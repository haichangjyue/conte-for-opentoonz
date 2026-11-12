# SPDX-License-Identifier: BSD-3-Clause
"""P4 模板/字体/溢出/超框 单测。"""
import sys
import tempfile
import unittest
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))
sys.path.insert(0, str(POC / "tools"))

import make_demo  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from konte_poc import minischema, render, textfit, template as tplmod  # noqa: E402
from konte_poc.model import KonteProject  # noqa: E402


class TestTemplateConfig(unittest.TestCase):
    def test_default_template_coords(self):
        t = tplmod.default_template()
        self.assertEqual(t.id, "scfilms_storyboard")
        self.assertEqual(t.canvas, (2480, 3507))
        self.assertEqual(t.dpi, 300)
        self.assertEqual(t.per_page, 5)
        self.assertEqual(len(t.rows), 5)
        self.assertEqual((t.rows[0].y0, t.rows[-1].y1), (417, 3276))
        self.assertEqual((t.columns["cut"].x0, t.columns["duration"].x1), (96, 2376))
        self.assertEqual(t.header.y0, 354)

    def test_default_matches_layout_shim(self):
        from konte_poc import layout
        t = tplmod.default_template()
        self.assertEqual(layout.CANVAS_W, t.canvas_w)
        self.assertEqual(layout.ROW_TOPS, [r.y0 for r in t.rows])
        self.assertEqual(layout.PIC_X0, t.columns["picture"].x0)

    def test_schema_validates_template(self):
        import json
        data = json.loads(tplmod.DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8"))
        schema = json.loads(tplmod.SCHEMA_PATH.read_text(encoding="utf-8"))
        errs = minischema.validate(data, schema)
        self.assertEqual(errs, [], msg=str(errs))

    def test_invalid_perpage_mismatch(self):
        import json
        data = json.loads(tplmod.DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8"))
        data["perPage"] = 4  # 但 cuts 仍 5 行 → 语义冲突
        with self.assertRaises(tplmod.TemplateError):
            tplmod.from_dict(data)

    def test_variant_4cut(self):
        p = tplmod.TEMPLATE_DIR / "scfilms_storyboard_4cut.json"
        t = tplmod.load_template(p)
        self.assertEqual(t.per_page, 4)
        self.assertEqual(len(t.rows), 4)
        self.assertIsNone(t.base_psd)

    def test_default_font_is_source_han(self):
        t = tplmod.default_template()
        self.assertEqual(t.font("default").family, "Source Han Sans")
        self.assertGreaterEqual(t.font("pageNo").size, 50)


class TestFontsAndText(unittest.TestCase):
    def test_default_family_resolves(self):
        name = textfit.resolved_family()
        self.assertTrue(name and "SourceHanSans" in name, msg=str(name))

    def test_font_family_resolution(self):
        name = textfit.resolved_family("Noto Sans JP")
        self.assertTrue(name and "Noto" in name, msg=str(name))
        f = textfit.get_font(24, family="Noto Sans JP")
        self.assertTrue(hasattr(f, "getlength"))

    def test_ellipsis_overflow(self):
        font = textfit.get_font(20, family="Noto Sans JP")
        lines = textfit.wrap("あ" * 200, font, 120, kinsoku=True)
        self.assertGreater(len(lines), 2)
        out, truncated = textfit._apply_overflow(lines, font, 120, 40, 24, "ellipsis", 2)
        self.assertTrue(truncated)
        self.assertLessEqual(len(out), 2)
        self.assertTrue(out[-1].endswith("…"), msg=out[-1])

    def test_kinsoku_no_trailing_comma_start(self):
        font = textfit.get_font(20, family="Noto Sans JP")
        # 构造一个标点会被挤到行首的文本
        text = "あいうえおかきくけこ、さしすせそ"
        lines = textfit.wrap(text, font, 100, kinsoku=True)
        for ln in lines[1:]:
            self.assertFalse(ln[:1] in "、。，", msg=f"行首禁则失效: {lines}")

    def test_fit_block_runs(self):
        im = Image.new("RGB", (200, 120), (255, 255, 255))
        d = ImageDraw.Draw(im)
        used = textfit.fit_block(d, "テスト台詞、長い文章の折り返し確認。", (2, 2, 198, 118),
                                 size=28, family="Noto Sans JP", overflow="ellipsis",
                                 max_lines=2, kinsoku=True)
        self.assertGreaterEqual(used, 14)


class TestBleedAndRender(unittest.TestCase):
    def _wide_panel(self):
        im = Image.new("RGB", (2400, 1080), (200, 220, 240))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 100, 1080], fill=(220, 60, 60))
        d.rectangle([2300, 0, 2400, 1080], fill=(60, 60, 220))
        return im

    def test_cover_vs_contain_differ(self):
        panel = self._wide_panel()
        a = Image.new("RGB", (400, 300), (255, 255, 255))
        b = a.copy()
        ra = render.paste_picture(a, panel, (0, 0, 400, 300), inset=0, mode="contain")
        rb = render.paste_picture(b, panel, (0, 0, 400, 300), inset=0, mode="cover")
        self.assertFalse(ra["cropped"])
        self.assertTrue(rb["cropped"])
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_bleed_indicator_changes_pixels(self):
        panel = self._wide_panel()
        a = Image.new("RGB", (400, 300), (255, 255, 255))
        b = a.copy()
        render.paste_picture(a, panel, (0, 0, 400, 300), inset=0, mode="cover")
        render.paste_picture(b, panel, (0, 0, 400, 300), inset=0, mode="cover", bleed_indicator=True)
        self.assertNotEqual(a.tobytes(), b.tobytes())


class TestMultiTemplateRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="konte_tpl_"))
        cls.proj_path = make_demo.make(cls.tmp / "EP01")
        cls.project = KonteProject.load(cls.proj_path)
        cls.variant = tplmod.load_template(tplmod.TEMPLATE_DIR / "scfilms_storyboard_4cut.json")

    def test_default_pages(self):
        from konte_poc import pdfgen
        imgs, infos = pdfgen.compose_pages(self.project, base_psd="", template=None)
        self.assertEqual(len(imgs), 2)  # 7 cuts / 5
        self.assertEqual(imgs[0].size, (2480, 3507))
        self.assertEqual(len(infos[0]["cutIds"]), 5)

    def test_variant_pages(self):
        from konte_poc import pdfgen
        imgs, infos = pdfgen.compose_pages(self.project, base_psd="", template=self.variant)
        self.assertEqual(len(imgs), 2)  # 7 cuts / 4 → 4 + 3
        self.assertEqual(imgs[0].size, (2480, 3507))
        self.assertEqual(len(infos[0]["cutIds"]), 4)
        self.assertEqual(len(infos[1]["cutIds"]), 3)


if __name__ == "__main__":
    unittest.main()
