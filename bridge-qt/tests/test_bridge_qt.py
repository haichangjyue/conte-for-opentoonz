# SPDX-License-Identifier: BSD-3-Clause
"""konte-bridge-qt（Qt5 原生服务）端到端冒烟测试。

启动 build/bridge-qt/konte-bridge-qt.exe，走 health→pair→project/cuts→update→lock→WS→export。
若可执行文件不存在则跳过（需先 scripts/build_bridge_qt.ps1）。
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POC = REPO / "poc"
sys.path.insert(0, str(POC / "tools"))
import make_demo  # noqa: E402
from PIL import Image  # noqa: E402

EXE = REPO / "build" / "bridge-qt" / "konte-bridge-qt.exe"
QT_BIN = Path(os.environ.get("KONTE_QT_BIN", r"X:\agent\tools\Qt\5.15.2\msvc2019_64\bin"))
QT_PLUGINS = QT_BIN.parent / "plugins"


def _png_bytes():
    import io
    im = Image.new("RGB", (320, 180), (240, 230, 210))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipUnless(EXE.exists(), f"未构建 Qt bridge: {EXE}")
class TestBridgeQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="konte_bridge_qt_"))
        cls.proj = make_demo.make(cls.tmp / "EP01")
        cls.port = _free_port()
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join([str(EXE.parent), str(QT_BIN), str(Path(sys.executable).parent),
                                       env.get("PATH", "")])
        env["QT_PLUGIN_PATH"] = str(QT_PLUGINS)
        cls.proc = subprocess.Popen(
            [str(EXE), "--project", str(cls.proj), "--host", "127.0.0.1",
             "--port", str(cls.port), "--pin", "482913",
             "--py", sys.executable, "--poc", str(POC)],
            cwd=str(POC), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.token = None
        # 等健康
        for _ in range(100):
            try:
                code, _ = cls.req_cls("GET", "/api/health", token=False)
                if code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            out = cls.proc.stdout.read() if cls.proc.stdout else ""
            raise RuntimeError("Qt bridge 未就绪: " + out)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.proc.terminate()
            cls.proc.wait(timeout=5)
        except Exception:
            cls.proc.kill()

    @classmethod
    def req_cls(cls, method, path, body=None, token=True, ctype="application/json"):
        url = cls.base + path
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        headers = {}
        if ctype:
            headers["Content-Type"] = ctype
        if token and cls.token:
            headers["Authorization"] = "Bearer " + cls.token
        r = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def req(self, method, path, body=None, token=True, ctype="application/json"):
        return self.req_cls(method, path, body=body, token=token, ctype=ctype)

    def test_01_health_pair(self):
        code, body = self.req("GET", "/api/health", token=False)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])
        code, _ = self.req("POST", "/api/pair", {"pin": "000000", "deviceName": "x"}, token=False)
        self.assertEqual(code, 401)
        code, body = self.req("POST", "/api/pair", {"pin": "482913", "deviceName": "iPad"}, token=False)
        self.assertEqual(code, 200)
        TestBridgeQt.token = json.loads(body)["token"]

    def test_02_project_cuts(self):
        code, body = self.req("GET", "/api/project")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "final")
        code, body = self.req("GET", "/api/cuts")
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(body)["items"]), 7)

    def test_03_update_and_lock(self):
        code, body = self.req("GET", "/api/cuts/ep01-c001")
        rev = json.loads(body)["revision"]
        code, body = self.req("PUT", "/api/cuts/ep01-c001", {"action": "qt 改", "expectedRevision": rev})
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)["revision"], rev + 1)
        code, _ = self.req("POST", "/api/cuts/ep01-c002/lock", {"ttl": 60})
        self.assertEqual(code, 200)
        code, _ = self.req("DELETE", "/api/cuts/ep01-c002/lock")
        self.assertEqual(code, 200)

    def test_04_ws_handshake(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        s.sendall((f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                   "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = s.recv(1024).decode("latin-1")
        self.assertIn("101 Switching Protocols", head)
        s.close()

    def test_05_export_job(self):
        code, body = self.req("POST", "/api/export", {"targets": {"pdf": True, "scenes": True}})
        self.assertEqual(code, 202, body)
        job_id = json.loads(body)["jobId"]
        status = None
        for _ in range(120):
            code, body = self.req("GET", f"/api/export/{job_id}")
            status = json.loads(body)["status"]
            if status in ("done", "failed"):
                break
            time.sleep(0.5)
        self.assertEqual(status, "done", body)
        outs = json.loads(body)["outputs"]
        self.assertTrue(Path(outs[0]).exists(), outs)

    def test_06_drawing_upload(self):
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
        data = json.loads(resp)
        self.assertIn("thumbnailUrl", data)
        self.assertGreater(data["revision"], 1)
        code, _ = self.req("GET", "/api/cuts/ep01-c003/thumbnail")
        self.assertEqual(code, 200)


    def test_07_create_cut_and_panels(self):
        # 新建镜头
        code, body = self.req("POST", "/api/cuts", {})
        self.assertEqual(code, 201, body)
        cut = json.loads(body)["cut"]
        self.assertEqual(cut["number"], 8)
        self.assertEqual(cut["cut"], "8", "CUT 号应为纯数字")
        cid = cut["id"]
        code, body = self.req("GET", "/api/cuts")
        items = json.loads(body)["items"]
        self.assertEqual(len(items), 8)
        self.assertEqual(items[-1]["number"], 8)

        # 加一格
        code, body = self.req("POST", f"/api/cuts/{cid}/panels", {})
        self.assertEqual(code, 201, body)
        self.assertEqual(json.loads(body)["index"], 1)
        self.assertEqual(json.loads(body)["panelCount"], 2)

        # 写入第 2 格（drawingIndex=1）
        boundary = "----konteboundary2"
        payload = _png_bytes()
        parts = []
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"frameKind\"\r\n\r\nstandard\r\n".encode())
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"drawingIndex\"\r\n\r\n1\r\n".encode())
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"p.png\"\r\n"
                      f"Content-Type: image/png\r\n\r\n").encode() + payload + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        mbody = b"".join(parts)
        code, resp = self.req("POST", f"/api/cuts/{cid}/drawing", mbody,
                              ctype=f"multipart/form-data; boundary={boundary}")
        self.assertEqual(code, 200, resp)
        data = json.loads(resp)
        self.assertEqual(data["index"], 1)
        self.assertEqual(data["panelCount"], 2)

        # 第 2 格缩略图可取
        code, _ = self.req("GET", f"/api/cuts/{cid}/panels/1/thumbnail")
        self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()
