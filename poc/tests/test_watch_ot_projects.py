# SPDX-License-Identifier: BSD-3-Clause
"""OT 项目目录监听器的单元/冒烟测试（不真正起浏览器）。

覆盖：
  * scan_projects 递归发现 + 跳过内部目录
  * diff_new 只报告新增项目
  * main(--once --launch-existing --dry-run) 输出计划且不启动子进程
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_POC))
sys.path.insert(0, str(_POC / "tools"))

import watch_ot_projects as W  # noqa: E402


class WatchOtProjectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _mk(self, rel: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")
        return p

    def test_scan_recurses_and_skips_internal(self):
        a = self._mk("EP01/konte.json")
        b = self._mk("EP02/scenes/konte.json")
        self._mk("EP02/.bridge/konte.json")       # 应跳过
        self._mk("EP02/node_modules/konte.json")  # 应跳过
        got = set(W.scan_projects(self.root))
        self.assertIn(str(a.resolve()), got)
        self.assertIn(str(b.resolve()), got)
        self.assertEqual(len(got), 2)

    def test_diff_new(self):
        prev = {"a": 1.0, "b": 2.0}
        cur = {"a": 1.0, "b": 2.0, "c": 3.0}
        self.assertEqual(W.diff_new(prev, cur), ["c"])
        self.assertEqual(W.diff_new(cur, cur), [])

    def test_main_dry_run_once_lists_projects(self):
        a = self._mk("P1/konte.json")
        _ = self._mk("P2/konte.json")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = W.main(["--root", str(self.root), "--once",
                           "--launch-existing", "--dry-run"])
        self.assertEqual(code, 0)
        lines = [json.loads(x) for x in buf.getvalue().splitlines() if x.strip()]
        events = [x for x in lines if x.get("event") == "wouldLaunch"]
        self.assertEqual(len(events), 2)
        self.assertIn(str(a.resolve()), [e["project"] for e in events])


if __name__ == "__main__":
    unittest.main()
