# SPDX-License-Identifier: BSD-3-Clause
"""P5 批量导出（断点续/进度日志/失败汇总/>200 cut）单测。"""
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))
sys.path.insert(0, str(POC / "tools"))

from konte_poc import minischema  # noqa: E402
from konte_poc.batch import export_batch  # noqa: E402
from _fixtures import make_project  # noqa: E402

FAKE_EXPORTER = r'''
import argparse, hashlib, json, os, sys
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument("--sceneplans", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--template", default=None)
a = ap.parse_args()
sp = Path(a.sceneplans); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
fail = os.environ.get("KONTE_FAKE_FAIL") == "1"
count = 0
for p in sorted(sp.glob("*.sceneplan.json")):
    if fail:
        continue
    stem = p.name[:-len(".sceneplan.json")]
    (out / (stem + ".tnz")).write_text("TNZ " + hashlib.sha1(p.read_bytes()).hexdigest(), encoding="utf-8")
    count += 1
marker = os.environ.get("KONTE_FAKE_LOG")
if marker:
    with open(marker, "a", encoding="utf-8") as f:
        f.write(str(count) + "\n")
sys.exit(1 if (fail and count == 0) else 0)
'''


def _write_fake(dirp: Path) -> Path:
    p = dirp / "fake_export.py"
    p.write_text(FAKE_EXPORTER, encoding="utf-8")
    return p


def _make_project_file(dirp: Path, n: int, fps: int = 24, frame=(320, 180)) -> Path:
    d = make_project(n)
    d["project"]["fps"] = fps
    w, h = frame
    d["project"]["frame"] = {"width": w, "height": h, "aspect": "16:9"}
    d["project"]["cameraBox"] = {"x": 0, "y": 0, "w": w, "h": h}
    for c in d["cuts"]:
        c["frame"]["rect"] = {"x": 0, "y": 0, "w": w, "h": h}
        dur = c["duration"]
        if dur["status"] == "fixed":
            dur["totalFrames"] = dur["seconds"] * fps + dur["frames"]
    p = dirp / "konte.json"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


class TestBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="konte_batch_"))
        self.fake = _write_fake(self.tmp)
        self.marker = self.tmp / "fake_calls.txt"
        os.environ["KONTE_FAKE_LOG"] = str(self.marker)

    def tearDown(self):
        for k in ("KONTE_FAKE_LOG", "KONTE_FAKE_FAIL"):
            os.environ.pop(k, None)

    def test_batch_250_and_resume(self):
        proj = _make_project_file(self.tmp, 250)
        out = self.tmp / "out"
        r1 = export_batch(proj, out, make_pdf=False, exporter=self.fake, quiet=True)
        self.assertEqual(r1["cutCount"], 250)
        self.assertEqual(r1["tnzGenerated"], 250)
        self.assertTrue(r1["ok"], msg=r1["failed"])
        self.assertTrue((out / "export_log.jsonl").exists())
        man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(man["items"]), 250)
        schema = json.loads((POC.parent / "konte-format" / "manifest.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(minischema.validate(man, schema), [])
        # 断点续：全部复用、内核不再被调用
        r2 = export_batch(proj, out, make_pdf=False, exporter=self.fake, quiet=True)
        self.assertEqual(r2["tnzGenerated"], 0)
        self.assertEqual(r2["tnzReused"], 250)
        self.assertEqual(r2["rendered"], 0)
        self.assertEqual(r2["planWritten"], 0)
        self.assertTrue(r2["ok"])
        calls = [x for x in self.marker.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual(calls, ["250"], msg=f"exporter 调用记录异常: {calls}")

    def test_batch_exporter_failure_marks_failed(self):
        os.environ["KONTE_FAKE_FAIL"] = "1"
        proj = _make_project_file(self.tmp, 3)
        out = self.tmp / "out_fail"
        r = export_batch(proj, out, make_pdf=False, exporter=self.fake, quiet=True)
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["failed"]), 3)
        self.assertEqual(r["status"], "failed")

    def test_batch_pdf_small(self):
        import make_demo
        proj = make_demo.make(self.tmp / "EP01")
        out = self.tmp / "out_pdf"
        r = export_batch(proj, out, base_psd="", make_pdf=True, exporter=None, quiet=True, resume=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["cutCount"], 7)
        self.assertEqual(r["pageCount"], 2)
        self.assertTrue((out / "storyboard.pdf").exists())
        self.assertFalse(r["pdfReused"])

    def test_batch_different_fps(self):
        proj = _make_project_file(self.tmp, 4, fps=30)
        out = self.tmp / "out_fps"
        r = export_batch(proj, out, make_pdf=False, exporter=self.fake, quiet=True)
        self.assertEqual(r["cutCount"], 4)
        self.assertEqual(r["totalFrames"], 4 * 60)  # 2s * 30fps
        self.assertTrue(r["ok"])


if __name__ == "__main__":
    unittest.main()
