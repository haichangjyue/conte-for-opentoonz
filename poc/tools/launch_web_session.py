#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""一键 Web 会话启动器（OT 单项目会话）。

一个进程内同时托管：
  * Bridge（konte_bridge，读写 konte.json / 图片上传 / 缩略图 / 导出）
  * Web 编辑器静态站（repos/konte-studio/web）

并自动完成「连接信息下发」：
  * 随机 6 位 PIN（也可 --pin 指定）
  * 启动器自动用 PIN 配对一次，拿到 token
  * 组装带 query 的深链 URL：?bridge=...&token=...&pin=...&desktop=1
  * 打开浏览器（默认）或只打印 URL（--no-open）

Web 端读取 query 后即自动连接（无需手填 Bridge/PIN）。

用法：
  python poc/tools/launch_web_session.py --project poc/examples/EP01/konte.json
  python poc/tools/launch_web_session.py --project ... --no-open --session-file s.json --json
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import secrets
import signal
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

# ---- 让本脚本可直接运行（不依赖已安装包） ----
_HERE = Path(__file__).resolve()
_REPO1 = _HERE.parents[2]          # .../repos/konte-for-opentoonz
_REPOS = _HERE.parents[3]          # .../repos
for _p in (_REPO1 / "poc", _REPO1 / "bridge" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _find_web_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("KONTE_WEB_ROOT")
    if env:
        return Path(env).resolve()
    cand = _REPOS / "konte-studio" / "web"
    return cand.resolve()


def _free_port(host: str, preferred: int) -> int:
    """优先用 preferred；被占用则退回系统分配（0）。"""
    for port in ([preferred] if preferred else []) + [0]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            p = s.getsockname()[1]
            s.close()
            return p
        except OSError:
            s.close()
    raise RuntimeError("无法分配端口")


class _WebHandler(SimpleHTTPRequestHandler):
    """静态站：禁缓存、禁目录列表、CORS 放开；支持 /go 跳转到带连接参数的深链。"""

    redirect_to: str | None = None

    def do_GET(self):  # noqa: N802
        target = getattr(self.__class__, "redirect_to", None)
        if target and (self.path == "/go" or self.path.startswith("/go?")):
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self):  # noqa: N802
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt, *args):  # 静默
        pass


def _wait_health(base: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                return json.load(r)
        except Exception as e:  # 服务尚未就绪
            last_err = e
            time.sleep(0.15)
    raise RuntimeError(f"Bridge 健康检查超时: {last_err}")


def _pair(base: str, pin: str) -> dict:
    data = json.dumps({"pin": pin, "deviceName": "desktop-launcher"}).encode("utf-8")
    req = urllib.request.Request(base + "/api/pair", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def _lan_ip() -> str:
    """本机在局域网中的 IPv4（供 iPad/平板访问）；失败回退 hostname 解析。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def build_url(host: str, web_port: int, bridge_port: int, token: str | None, pin: str) -> str:
    q = {"bridge": f"http://{host}:{bridge_port}", "desktop": "1"}
    if token:
        q["token"] = token
    q["pin"] = pin
    return f"http://{host}:{web_port}/?{urlencode(q)}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="launch-web-session",
                                 description="一键启动 NARRATIVISM Web 会话（Bridge + Web）")
    ap.add_argument("--project", required=True, help="konte.json 路径")
    ap.add_argument("--web-root", default=None, help="Web 静态目录（默认 repos/konte-studio/web）")
    ap.add_argument("--host", default="127.0.0.1", help="绑定地址；平板/iPad 访问用 0.0.0.0")
    ap.add_argument("--public-host", default=None,
                    help="对外 URL 主机（默认：绑定 0.0.0.0 时自动取局域网 IPv4）")
    ap.add_argument("--bridge-port", type=int, default=17890)
    ap.add_argument("--web-port", type=int, default=5173)
    ap.add_argument("--pin", default=None, help="配对 PIN（默认随机 6 位）")
    ap.add_argument("--base-psd", default=None, help="导出 PDF 底版 PSD（可选）")
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--session-file", default=None, help="会话信息 JSON 落盘路径")
    ap.add_argument("--json", action="store_true", help="stdout 只输出一行 JSON")
    ap.add_argument("--ready-timeout", type=float, default=20.0)
    args = ap.parse_args(argv)

    project = Path(args.project).resolve()
    if not project.exists():
        print(f"[launch] 找不到项目: {project}", file=sys.stderr)
        return 2
    web_root = _find_web_root(args.web_root)
    if not (web_root / "index.html").exists():
        print(f"[launch] Web 根目录无效（缺 index.html）: {web_root}", file=sys.stderr)
        return 2

    from konte_bridge.server import create_server  # 延迟导入，确保 sys.path 生效

    bind = args.host
    connect_host = "127.0.0.1" if bind in ("0.0.0.0", "", "::") else bind
    if args.public_host:
        public_host = args.public_host
    elif bind in ("0.0.0.0", "", "::"):
        public_host = _lan_ip()
    else:
        public_host = bind

    pin = args.pin or f"{secrets.randbelow(1000000):06d}"
    bport = _free_port(connect_host, args.bridge_port)
    wport = _free_port(connect_host, args.web_port)
    while wport == bport:
        wport = _free_port(connect_host, 0)

    httpd = create_server(project, host=bind, port=bport, pin=pin,
                          base_psd=args.base_psd)
    t_bridge = threading.Thread(target=httpd.serve_forever, name="bridge", daemon=True)
    t_bridge.start()

    web = ThreadingHTTPServer(
        (bind, wport),
        functools.partial(_WebHandler, directory=str(web_root)),
    )
    t_web = threading.Thread(target=web.serve_forever, name="web", daemon=True)
    t_web.start()

    base = f"http://{connect_host}:{bport}"
    health = _wait_health(base, timeout=args.ready_timeout)
    token = None
    try:
        token = _pair(base, pin).get("token")
    except Exception as e:  # token 下发失败不致命，Web 仍可用 PIN 自动配对
        if not args.json:
            print(f"[launch] 预配对失败（Web 将回退 PIN 配对）: {e}", file=sys.stderr)

    url = build_url(public_host, wport, bport, token, pin)
    _WebHandler.redirect_to = url
    session = {
        "ok": True,
        "project": str(project),
        "title": health.get("project"),
        "host": public_host,
        "bindHost": bind,
        "bridgePort": bport,
        "webPort": wport,
        "bridgeUrl": f"http://{public_host}:{bport}",
        "webUrl": f"http://{public_host}:{wport}/",
        "goUrl": f"http://{public_host}:{wport}/go",
        "url": url,
        "pin": pin,
        "token": token,
        "pid": os.getpid(),
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    if args.session_file:
        sf = Path(args.session_file).resolve()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(session, ensure_ascii=False))
    else:
        print("[launch] NARRATIVISM Web 会话已就绪")
        print(f"  项目   : {project}")
        print(f"  Bridge : {session['bridgeUrl']}")
        print(f"  Web    : {session['webUrl']}")
        print(f"  PIN    : {pin}")
        print(f"  URL    : {url}")
        print(f"  短链   : {session['goUrl']}  （打开即自动连接）")
        if session["bindHost"] in ("0.0.0.0", "", "::"):
            print(f"  平板/iPad: 同一局域网，打开上面的“短链”（主机 {public_host}）")

    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    stop = threading.Event()

    def _shutdown(*_a):
        stop.set()

    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, _shutdown)
            except (ValueError, OSError):
                pass

    try:
        while not stop.is_set():
            stop.wait(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if not args.json:
            print("\n[launch] 正在关闭会话…")
        try:
            web.shutdown()
            web.server_close()
        except Exception:
            pass
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
