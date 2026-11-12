# SPDX-License-Identifier: BSD-3-Clause
"""一键 Web 会话启动器的单元/冒烟测试（不启动浏览器）。

覆盖：
  * build_url 深链拼装（含 token/pin/desktop）
  * _free_port 分配
  * create_server 起 Bridge 线程 → health → pair（启动器核心链路）
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

_POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_POC))
sys.path.insert(0, str(_POC / "tools"))

import launch_web_session as L  # noqa: E402


class LaunchWebSessionTests(unittest.TestCase):
    def test_build_url_contains_params(self):
        url = L.build_url("127.0.0.1", 5173, 17890, "TOK123", "482913")
        self.assertTrue(url.startswith("http://127.0.0.1:5173/?"))
        self.assertIn("bridge=http%3A%2F%2F127.0.0.1%3A17890", url)
        self.assertIn("token=TOK123", url)
        self.assertIn("pin=482913", url)
        self.assertIn("desktop=1", url)

    def test_build_url_without_token(self):
        url = L.build_url("127.0.0.1", 5173, 17890, None, "000001")
        self.assertNotIn("token=", url)
        self.assertIn("pin=000001", url)

    def test_free_port(self):
        p = L._free_port("127.0.0.1", 0)
        self.assertIsInstance(p, int)
        self.assertGreater(p, 0)

    def test_bridge_thread_health_and_pair(self):
        import shutil
        import tempfile

        from konte_bridge.server import create_server

        src = _POC / "examples" / "EP01" / "konte.json"
        if not src.exists():
            self.skipTest("缺少 EP01 示例")
        # 复制到临时目录，避免在 examples/ 下生成 .bridge 等运行产物
        tmp = tempfile.TemporaryDirectory()
        try:
            project = Path(tmp.name) / "konte.json"
            shutil.copyfile(src, project)
            httpd = create_server(project, host="127.0.0.1", port=0, pin="482913")
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            base = f"http://127.0.0.1:{port}"
            try:
                health = L._wait_health(base, timeout=10)
                self.assertTrue(health.get("ok"))
                self.assertEqual(health.get("project"), "EP01")
                res = L._pair(base, "482913")
                self.assertTrue(res.get("token"))
            finally:
                httpd.shutdown()
                httpd.server_close()
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
