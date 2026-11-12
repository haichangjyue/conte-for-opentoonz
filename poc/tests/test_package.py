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
from konte_poc.package import build_package  # noqa: E402


class TestPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="konte_pkg_"))
        cls.proj = make_demo.make(cls.tmp / "EP01")
        cls.root = cls.tmp / "deliverables"
        # 不提供 exporter：验证结构包（无 .tnz，但有 PDF/manifest/references/zip）
        cls.report = build_package(cls.proj, cls.root, base_psd=None, exporter=None)

    def test_structure(self):
        pkg = self.root / "EP01"
        self.assertTrue((pkg / "references").is_dir())
        self.assertTrue((pkg / "scenes").is_dir())
        self.assertTrue((pkg / "storyboard.pdf").exists())
        self.assertTrue((pkg / "manifest.json").exists())
        self.assertTrue((pkg / "DELIVERY.md").exists())

    def test_manifest_schema(self):
        pkg = self.root / "EP01"
        man = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(man["items"]), 7)
        self.assertTrue(all("sceneFile" in it for it in man["items"]))

    def test_references(self):
        pkg = self.root / "EP01"
        self.assertEqual(len(list((pkg / "references").glob("*.png"))), 7)

    def test_verify_ok_without_tnz(self):
        self.assertTrue(self.report["verify"]["ok"])
        self.assertGreaterEqual(len(self.report["verify"]["warnings"]), 1)

    def test_zip(self):
        z = Path(self.report["zip"])
        self.assertTrue(z.exists())
        self.assertGreater(z.stat().st_size, 10000)


if __name__ == "__main__":
    unittest.main()
