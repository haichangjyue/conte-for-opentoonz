# SPDX-License-Identifier: BSD-3-Clause
"""Bridge 生产化加固单测：token TTL / 上传限速 / PIN 锁定 / 锁过期 / 任务清理 / health。"""
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path

BRIDGE_SRC = Path(__file__).resolve().parents[1] / "src"
POC = Path(__file__).resolve().parents[2] / "poc"
sys.path.insert(0, str(BRIDGE_SRC))
sys.path.insert(0, str(POC))
sys.path.insert(0, str(POC / "tools"))

import make_demo  # noqa: E402
from konte_bridge.store import ApiError, Store  # noqa: E402
from PIL import Image  # noqa: E402


def _png():
    im = Image.new("RGB", (160, 90), (230, 220, 200))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class TestStoreHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="konte_hard_"))
        cls.proj = make_demo.make(cls.tmp / "EP01")

    def _store(self, **kw):
        return Store(self.proj, pin="111111", **kw)

    def test_token_ttl_expiry(self):
        s = self._store(token_ttl=0)
        tok = s.pair("111111", "ipad")["token"]
        with self.assertRaises(ApiError) as ctx:
            s.auth(tok)
        self.assertEqual(ctx.exception.status, 401)

    def test_pair_bruteforce_lock(self):
        s = self._store(max_pair_fail=2, pair_fail_window=60)
        for _ in range(2):
            with self.assertRaises(ApiError) as c:
                s.pair("000000", "x", client="1.2.3.4")
            self.assertEqual(c.exception.status, 401)
        with self.assertRaises(ApiError) as c:
            s.pair("000000", "x", client="1.2.3.4")
        self.assertEqual(c.exception.status, 429)

    def test_upload_rate_limit(self):
        s = self._store(max_uploads_per_min=2)
        png = _png()
        s.save_drawing("ep01-c001", png, device_id="dev-a")
        s.save_drawing("ep01-c001", png, device_id="dev-a")
        with self.assertRaises(ApiError) as c:
            s.save_drawing("ep01-c001", png, device_id="dev-a")
        self.assertEqual(c.exception.status, 429)
        # 另一设备不受影响
        s.save_drawing("ep01-c001", png, device_id="dev-b")

    def test_lock_ttl_expires(self):
        s = self._store()
        s.lock("ep01-c002", "dev-1", ttl=1)
        time.sleep(1.1)
        cut = s.get_cut("ep01-c002")
        self.assertIsNone(cut["lock"])
        # 过期后其他设备可拿锁
        res = s.lock("ep01-c002", "dev-2", ttl=60)
        self.assertTrue(res["locked"])

    def test_job_prune(self):
        s = self._store(job_ttl=1, max_jobs=2)
        now = time.time()
        for i in range(3):
            s.jobs[f"old{i}"] = {"status": "done", "createdAt": now - 100, "endedAt": now - 100}
        s._prune_jobs(now)
        self.assertEqual(len(s.jobs), 0)  # 全部过期
        for i in range(5):
            s.jobs[f"new{i}"] = {"status": "done", "createdAt": now, "endedAt": now}
        s._prune_jobs(now)
        self.assertEqual(len(s.jobs), 2)  # 仅保留上限内

    def test_health(self):
        s = self._store()
        h = s.health()
        self.assertTrue(h["ok"])
        self.assertIn("uptimeSec", h)
        self.assertEqual(h["project"], "EP01")


if __name__ == "__main__":
    unittest.main()
