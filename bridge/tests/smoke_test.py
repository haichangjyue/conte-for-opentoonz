# SPDX-License-Identifier: BSD-3-Clause
"""Bridge sidecar 端到端冒烟测试（真实起 HTTP 服务，走一遍 OpenAPI 主要路径）。"""

import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BRIDGE_SRC = Path(__file__).resolve().parents[1] / "src"
POC = Path(__file__).resolve().parents[2] / "poc"
sys.path.insert(0, str(BRIDGE_SRC))
sys.path.insert(0, str(POC))
sys.path.insert(0, str(POC / "tools"))

import make_demo  # noqa: E402
from konte_bridge.server import create_server  # noqa: E402
from PIL import Image  # noqa: E402


def _png_bytes():
    im = Image.new("RGB", (320, 180), (240, 230, 210))
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, 300, 170], outline=(0, 0, 0), width=3)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class TestBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="konte_bridge_"))
        cls.proj = make_demo.make(cls.tmp / "EP01")
        cls.httpd = create_server(cls.proj, host="127.0.0.1", port=0, pin="482913")
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.token = None

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, method, path, body=None, token=True, ctype="application/json"):
        url = self.base + path
        data = body
        if isinstance(body, dict):
            data = json.dumps(body).encode()
        headers = {}
        if ctype:
            headers["Content-Type"] = ctype
        if token and self.token:
            headers["Authorization"] = "Bearer " + self.token
        r = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_01_unauthorized(self):
        code, _ = self.req("GET", "/api/project", token=False)
        self.assertEqual(code, 401)

    def test_02_pair_wrong_pin(self):
        code, _ = self.req("POST", "/api/pair", {"pin": "000000", "deviceName": "x"}, token=False)
        self.assertEqual(code, 401)

    def test_03_pair_ok(self):
        code, body = self.req("POST", "/api/pair", {"pin": "482913", "deviceName": "iPad"}, token=False)
        self.assertEqual(code, 200)
        data = json.loads(body)
        self.assertIn("token", data)
        TestBridge.token = data["token"]

    def test_04_project_and_cuts(self):
        code, body = self.req("GET", "/api/project")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "final")
        code, body = self.req("GET", "/api/cuts")
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(body)), 7)

    def test_05_get_and_update_cut(self):
        code, body = self.req("GET", "/api/cuts/ep01-c001")
        self.assertEqual(code, 200)
        rev = json.loads(body)["revision"]
        code, body = self.req("PUT", "/api/cuts/ep01-c001", {"action": "改：走位确认", "expectedRevision": rev})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["revision"], rev + 1)
        # 错误 revision → 409
        code, _ = self.req("PUT", "/api/cuts/ep01-c001", {"action": "x", "expectedRevision": rev})
        self.assertEqual(code, 409)

    def test_06_lock(self):
        code, _ = self.req("POST", "/api/cuts/ep01-c002/lock")
        self.assertEqual(code, 200)
        code, _ = self.req("DELETE", "/api/cuts/ep01-c002/lock")
        self.assertEqual(code, 200)

    def test_07_drawing_upload(self):
        boundary = "----konteboundary"
        payload = _png_bytes()
        parts = []
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"frameKind\"\r\n\r\nstandard\r\n".encode())
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"p.png\"\r\n"
                      f"Content-Type: image/png\r\n\r\n").encode() + payload + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        code, resp = self.req("POST", "/api/cuts/ep01-c003/drawing", body,
                              ctype=f"multipart/form-data; boundary={boundary}")
        self.assertEqual(code, 200, resp)
        self.assertIn("thumbnailUrl", json.loads(resp))
        code, _ = self.req("GET", "/api/cuts/ep01-c003/thumbnail")
        self.assertEqual(code, 200)

    def test_08_export_job(self):
        code, body = self.req("POST", "/api/export", {"targets": {"pdf": True, "scenes": True}})
        self.assertEqual(code, 202, body)
        job_id = json.loads(body)["jobId"]
        status = None
        for _ in range(60):
            code, body = self.req("GET", f"/api/export/{job_id}")
            status = json.loads(body)["status"]
            if status in ("done", "failed"):
                break
            time.sleep(0.5)
        self.assertEqual(status, "done", body)
        self.assertTrue(Path(json.loads(body)["outputs"][0]).exists())

    def test_09_ws_handshake(self):
        import socket
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        req = (f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        s.sendall(req.encode())
        head = s.recv(1024).decode("latin-1")
        self.assertIn("101 Switching Protocols", head)
        s.close()


if __name__ == "__main__":
    unittest.main()
