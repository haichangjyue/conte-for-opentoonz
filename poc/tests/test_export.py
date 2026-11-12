# SPDX-License-Identifier: BSD-3-Clause
import json
import sys
import tempfile
import unittest
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))
sys.path.insert(0, str(POC / "tools"))

import make_demo  # noqa: E402
from konte_poc import minischema  # noqa: E402
from konte_poc.export import export_project  # noqa: E402


class TestExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="konte_ep01_"))
        cls.proj_path = make_demo.make(cls.tmp / "EP01")
        cls.out = cls.tmp / "out"
        cls.report = export_project(cls.proj_path, cls.out, base_psd="")

    def test_report(self):
        self.assertEqual(self.report["cutCount"], 7)
        self.assertEqual(self.report["pageCount"], 2)
        self.assertEqual(self.report["totalFrames"], 408)

    def test_pdf_exists(self):
        pdf = self.out / "storyboard.pdf"
        self.assertTrue(pdf.exists())
        self.assertGreater(pdf.stat().st_size, 10000)

    def test_sceneplans(self):
        plans = list((self.out / "scenes").glob("*.sceneplan.json"))
        self.assertEqual(len(plans), 7)
        # 导出文件名规则：[项目名称]_[镜头号3位].tnz → EP01_001
        sp = self.out / "scenes" / "EP01_001.sceneplan.json"
        self.assertTrue(sp.exists(), "应使用 EP01_001 命名")
        data = json.loads(sp.read_text(encoding="utf-8"))
        self.assertEqual(data["sceneFile"], "EP01_001.tnz")
        self.assertEqual(data["duration"]["totalFrames"], 72)
        self.assertEqual(data["holdFrames"], {"from": 1, "to": 72})
        self.assertTrue(data["level"]["lock"])

    def test_references(self):
        refs = list((self.out / "references").glob("*.png"))
        self.assertEqual(len(refs), 7)

    def test_manifest_schema(self):
        man = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        schema = json.loads((POC.parent / "konte-format" / "manifest.schema.json").read_text(encoding="utf-8"))
        errs = minischema.validate(man, schema)
        self.assertEqual(errs, [], msg=str(errs))
        self.assertEqual(len(man["items"]), 7)

    def test_gate_blocks_draft(self):
        from konte_poc.errors import ExportGateError
        d = json.loads(self.proj_path.read_text(encoding="utf-8"))
        d["project"]["status"] = "draft"
        p = self.tmp / "EP01_draft.json"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ExportGateError):
            export_project(p, self.tmp / "out_draft", base_psd="")


if __name__ == "__main__":
    unittest.main()
