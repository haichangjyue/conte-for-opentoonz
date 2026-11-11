# SPDX-License-Identifier: BSD-3-Clause
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from konte_poc.errors import ExportGateError, InvariantError, SchemaError  # noqa: E402
from konte_poc.model import KonteProject  # noqa: E402

from _fixtures import clone, make_project  # noqa: E402


def load_via_file(data):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    import json
    json.dump(data, tmp, ensure_ascii=False)
    tmp.close()
    return KonteProject.load(tmp.name)


class TestModel(unittest.TestCase):
    def test_valid_project(self):
        p = load_via_file(make_project(3))
        self.assertEqual(p.fps, 24)
        self.assertEqual(len(p.sorted_cuts()), 3)
        self.assertEqual(p.total_frames(p.get_cut("c001")), 48)

    def test_schema_rejects_missing_field(self):
        d = make_project(1)
        del d["cuts"][0]["action"]
        with self.assertRaises(SchemaError):
            load_via_file(d)

    def test_schema_rejects_extra_field(self):
        d = make_project(1)
        d["cuts"][0]["bogus"] = 1
        with self.assertRaises(SchemaError):
            load_via_file(d)

    def test_duration_invariant(self):
        d = make_project(1)
        d["cuts"][0]["duration"]["totalFrames"] = 999
        with self.assertRaises(InvariantError):
            load_via_file(d)

    def test_gate_draft_blocks(self):
        p = load_via_file(make_project(2, status="draft"))
        with self.assertRaises(ExportGateError):
            p.check_export_gate()

    def test_gate_tbd_blocks(self):
        d = make_project(2)
        d["cuts"][1]["duration"] = {"status": "tbd", "totalFrames": 24}
        p = load_via_file(d)
        with self.assertRaises(ExportGateError) as ctx:
            p.check_export_gate()
        self.assertTrue(any("TBD" in x for x in ctx.exception.details))

    def test_gate_final_ok(self):
        p = load_via_file(make_project(2, status="final"))
        p.check_export_gate()  # 不抛


if __name__ == "__main__":
    unittest.main()
