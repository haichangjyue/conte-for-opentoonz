# SPDX-License-Identifier: BSD-3-Clause
"""Bridge sidecar HTTP + WebSocket 参考实现（零第三方依赖，stdlib）。

实现 bridge.openapi.yaml 的 9 条路径 + /ws 事件推送。
启动：python -m konte_bridge --project <konte.json> --host 127.0.0.1 --port 17890
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ws
from .store import ApiError, Store

MAX_UPLOAD = 10 * 1024 * 1024  # 10MB


def _route(path: str):
    """返回 (method_key, params) 供分发；method 由调用方区分。"""
    patterns = [
        (r"^/api/health$", "health"),
        (r"^/api/pair$", "pair"),
        (r"^/api/project$", "project"),
        (r"^/api/cuts$", "cuts"),
        (r"^/api/cuts/([^/]+)$", "cut"),
        (r"^/api/cuts/([^/]+)/drawing$", "drawing"),
        (r"^/api/cuts/([^/]+)/panels$", "panels"),
        (r"^/api/cuts/([^/]+)/panels/(\d+)/thumbnail$", "panel_thumb"),
        (r"^/api/cuts/([^/]+)/lock$", "lock"),
        (r"^/api/cuts/([^/]+)/thumbnail$", "thumbnail"),
        (r"^/api/export$", "export"),
        (r"^/api/export/([^/]+)$", "export_job"),
        (r"^/ws$", "ws"),
    ]
    for pat, name in patterns:
        m = re.match(pat, path)
        if m:
            return name, m.groups()
    return None, ()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "konte-bridge/0.1"

    # ---------- 基础响应 ----------
    def log_message(self, fmt, *args):  # 静默；需要时打开
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, ctype="application/octet-stream", status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, e: ApiError):
        self._send_json({"code": e.code, "message": e.message}, e.status)

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", 0) or 0)
        max_up = int(getattr(self.server, "max_upload", MAX_UPLOAD))
        if n > max_up:
            raise ApiError(413, "TOO_LARGE", f"上传过大（上限 {max_up} 字节）")
        return self.rfile.read(n) if n else b""

    def _read_json(self) -> dict:
        raw = self._read_body()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise ApiError(400, "BAD_JSON", "请求体不是合法 JSON")

    def _token(self) -> str | None:
        h = self.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            return h[7:].strip()
        return None

    def _auth(self) -> dict:
        return self.server.store.auth(self._token())

    # ---------- CORS ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        name, args = _route(parsed.path)
        if name == "ws":
            return self._handle_ws()
        try:
            if name == "health":
                return self._send_json(self.server.store.health())
            if name == "project":
                self._auth(); return self._send_json(self.server.store.project_info())
            if name == "cuts":
                self._auth(); return self._send_json(self.server.store.cuts_summary())
            if name == "cut":
                self._auth(); return self._send_json(self.server.store.get_cut(args[0]))
            if name == "thumbnail":
                self._auth()
                p = self.server.store.thumbnail_path(args[0])
                return self._send_bytes(p.read_bytes(), "image/png")
            if name == "panel_thumb":
                self._auth()
                p = self.server.store.thumbnail_path(args[0], int(args[1]))
                return self._send_bytes(p.read_bytes(), "image/png")
            if name == "export_job":
                self._auth(); return self._send_json(self.server.store.get_job(args[0]))
            self._send_json({"code": "NOT_FOUND", "message": "no route"}, 404)
        except ApiError as e:
            self._error(e)

    # ---------- POST ----------
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        name, args = _route(parsed.path)
        try:
            if name == "pair":
                body = self._read_json()
                client = self.client_address[0] if self.client_address else ""
                res = self.server.store.pair(body.get("pin", ""), body.get("deviceName", "device"),
                                             client=client)
                return self._send_json(res)
            if name == "cuts":
                self._auth()
                body = self._read_json()
                return self._send_json(self.server.store.create_cut(body), 201)
            if name == "panels":
                self._auth()
                return self._send_json(self.server.store.create_panel(args[0]), 201)
            if name == "drawing":
                self._auth()
                fields, image = self._parse_multipart(self._read_body())
                if not image:
                    raise ApiError(400, "NO_IMAGE", "缺少 image 文件")
                idx_raw = fields.get("drawingIndex")
                drawing_index = int(idx_raw) if idx_raw not in (None, "") else None
                res = self.server.store.save_drawing(
                    args[0], image,
                    frame_kind=fields.get("frameKind"),
                    device_id=fields.get("deviceId") or self._auth()["deviceId"],
                    drawing_index=drawing_index,
                )
                return self._send_json(res)
            if name == "lock":
                dev = self._auth()
                try:
                    body = self._read_json()
                except ApiError:
                    body = {}
                ttl = int(body.get("ttl", 120) or 120)
                return self._send_json(self.server.store.lock(args[0], dev["deviceId"], ttl=ttl))
            if name == "export":
                self._auth()
                body = self._read_json()
                job_id = self.server.store.start_export(body.get("targets"))
                return self._send_json({"jobId": job_id}, 202)
            self._send_json({"code": "NOT_FOUND", "message": "no route"}, 404)
        except ApiError as e:
            self._error(e)

    # ---------- PUT ----------
    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        name, args = _route(parsed.path)
        try:
            if name == "cut":
                self._auth()
                body = self._read_json()
                return self._send_json(self.server.store.update_cut(args[0], body))
            self._send_json({"code": "NOT_FOUND", "message": "no route"}, 404)
        except ApiError as e:
            self._error(e)

    # ---------- DELETE ----------
    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        name, args = _route(parsed.path)
        try:
            if name == "cut":
                self._auth()
                return self._send_json(self.server.store.delete_cut(args[0]))
            if name == "lock":
                dev = self._auth()
                return self._send_json(self.server.store.unlock(args[0], dev["deviceId"]))
            self._send_json({"code": "NOT_FOUND", "message": "no route"}, 404)
        except ApiError as e:
            self._error(e)

    # ---------- multipart ----------
    def _parse_multipart(self, body: bytes):
        ctype = self.headers.get("Content-Type", "")
        if "boundary=" not in ctype:
            raise ApiError(400, "BAD_MULTIPART", "缺少 multipart boundary")
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"')
        delim = ("--" + boundary).encode()
        fields: dict[str, str] = {}
        image = None
        for part in body.split(delim):
            if b"Content-Disposition" not in part:
                continue
            head, _, data = part.partition(b"\r\n\r\n")
            data = data.rstrip(b"\r\n")
            # 头里取 name
            m = re.search(rb'name="([^"]+)"', head)
            if not m:
                continue
            fname = m.group(1).decode()
            if fname == "image":
                image = data
            else:
                fields[fname] = data.decode("utf-8", "replace")
        return fields, image

    # ---------- WebSocket ----------
    def _handle_ws(self):
        resp = ws.handshake_response(self.headers)
        if not resp:
            return self._send_json({"code": "BAD_WS", "message": "缺少 Sec-WebSocket-Key"}, 400)
        self.connection.sendall(resp)
        self.close_connection = True
        hub = self.server.hub
        hub.add(self.connection)
        try:
            self.connection.sendall(ws.encode_text(json.dumps(
                {"event": "hello", "message": "konte bridge ws connected"})))
            while True:
                opcode, _data = ws.read_frame(self.connection)
                if opcode == 0x8:  # close
                    break
                if opcode == 0x9:  # ping → pong
                    self.connection.sendall(bytes([0x8A, 0]))
        except Exception:
            pass
        finally:
            hub.remove(self.connection)


def create_server(project_path: str | Path, *, host: str = "127.0.0.1", port: int = 17890,
                  pin: str | None = None, base_psd: str | None = None,
                  token_ttl: int = 12 * 3600, max_uploads_per_min: int = 60,
                  max_upload_mb: int = 10, job_ttl: int = 3600, max_jobs: int = 50):
    from .ws import Hub
    hub = Hub()
    store = Store(project_path, pin=pin, base_psd=base_psd, hub=hub,
                  token_ttl=token_ttl, max_uploads_per_min=max_uploads_per_min,
                  job_ttl=job_ttl, max_jobs=max_jobs)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.store = store
    httpd.hub = hub
    httpd.max_upload = int(max_upload_mb) * 1024 * 1024
    return httpd


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="konte-bridge", description="Konte Bridge sidecar")
    ap.add_argument("--project", required=True, help="konte.json 路径")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=17890)
    ap.add_argument("--pin", default=None, help="配对 PIN（默认随机 6 位）")
    ap.add_argument("--base-psd", default=None, help="PDF 底版 PSD")
    ap.add_argument("--token-ttl", type=int, default=12 * 3600, help="token 有效期（秒）")
    ap.add_argument("--max-uploads-per-min", type=int, default=60, help="每设备上传限速")
    ap.add_argument("--max-upload-mb", type=int, default=10, help="单次上传大小上限(MB)")
    ap.add_argument("--job-ttl", type=int, default=3600, help="导出任务保留秒数")
    ap.add_argument("--max-jobs", type=int, default=50, help="导出任务上限")
    args = ap.parse_args(argv)
    httpd = create_server(args.project, host=args.host, port=args.port,
                          pin=args.pin, base_psd=args.base_psd,
                          token_ttl=args.token_ttl,
                          max_uploads_per_min=args.max_uploads_per_min,
                          max_upload_mb=args.max_upload_mb,
                          job_ttl=args.job_ttl, max_jobs=args.max_jobs)
    print(f"[konte-bridge] listening http://{args.host}:{args.port}  PIN={httpd.store.pin}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[konte-bridge] bye")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    sys.exit(main())
