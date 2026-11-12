#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""OT 项目目录监听器 —— 「OT 侧自动拉起 Web 会话」。

产品会话模型（决策 #27）：一个 OT 项目 = 一个 Bridge/Web 会话。
本工具监听一个根目录，**发现新的 `konte.json` 项目文件时自动调用
`launch_web_session.py` 起一个会话并打开浏览器**，把「一键」变成「自动」。

它不修改 OpenToonz 二进制：OT 侧通过「项目落在被监听目录」即可触发；
若日后接入 OT 原生菜单（需重编 OT），只需在菜单动作里调用同一个启动器。

用法：
  # 常驻监听（新项目出现即拉起）
  python poc/tools/watch_ot_projects.py --root X:\\projects\\EP01
  # 只规划、不真正启动（CI/自检）
  python poc/tools/watch_ot_projects.py --root ... --once --launch-existing --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LAUNCHER = _HERE / "launch_web_session.py"

_SKIP_PARTS = {".bridge", ".konte_sessions", "node_modules", ".git", "__pycache__"}


def scan_projects(root: str | Path, pattern: str = "konte.json") -> dict[str, float]:
    """返回 {项目绝对路径: mtime}；跳过内部临时目录。"""
    root = Path(root)
    out: dict[str, float] = {}
    if not root.exists():
        return out
    for p in root.rglob(pattern):
        if any(part in _SKIP_PARTS for part in p.parts):
            continue
        try:
            out[str(p.resolve())] = p.stat().st_mtime
        except OSError:
            continue
    return out


def diff_new(prev: dict[str, float], cur: dict[str, float]) -> list[str]:
    """返回 cur 中相对 prev 新增的项目路径（按路径排序）。"""
    return sorted(set(cur) - set(prev))


def _session_file(root: Path, project: str) -> Path:
    h = hashlib.sha1(project.encode("utf-8")).hexdigest()[:10]
    d = root / ".konte_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.json"


def launch_session(project: str, root: Path, *, open_browser: bool,
                   log_dir: Path | None = None) -> subprocess.Popen | None:
    sf = _session_file(root, project)
    if sf.exists():
        try:
            sf.unlink()
        except OSError:
            pass
    cmd = [sys.executable, str(_LAUNCHER), "--project", project,
           "--bridge-port", "0", "--web-port", "0", "--session-file", str(sf)]
    if not open_browser:
        cmd.append("--no-open")
    log_dir = log_dir or (root / ".konte_sessions")
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "launcher.log", "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                cwd=str(_HERE))
    finally:
        log.close()
    return proc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="watch-ot-projects",
                                 description="监听 OT 项目目录，新项目自动拉起 Web 会话")
    ap.add_argument("--root", required=True, help="被监听的根目录")
    ap.add_argument("--pattern", default="konte.json", help="项目文件名（默认 konte.json）")
    ap.add_argument("--interval", type=float, default=2.0, help="轮询间隔秒")
    ap.add_argument("--once", action="store_true", help="扫描一次即退出")
    ap.add_argument("--launch-existing", action="store_true",
                    help="启动时也处理已存在项目（默认只看新增）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不真正启动")
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[watch] 根目录不存在: {root}", file=sys.stderr)
        return 2

    children: list[subprocess.Popen] = []

    def _handle(project: str):
        if args.dry_run:
            print(json.dumps({"event": "wouldLaunch", "project": project}, ensure_ascii=False))
            return
        proc = launch_session(project, root, open_browser=not args.no_open)
        if proc:
            children.append(proc)
            print(json.dumps({"event": "launched", "project": project, "pid": proc.pid},
                             ensure_ascii=False))

    try:
        if args.once:
            cur = scan_projects(root, args.pattern)
            todo = sorted(cur) if args.launch_existing else []
            for p in todo:
                _handle(p)
            if not todo:
                print(json.dumps({"event": "none", "root": str(root)}, ensure_ascii=False))
            return 0

        known = {} if args.launch_existing else scan_projects(root, args.pattern)
        if args.launch_existing:
            for p in sorted(known):
                _handle(p)
            known = scan_projects(root, args.pattern)
        print(json.dumps({"event": "watching", "root": str(root),
                          "known": len(known), "pattern": args.pattern}, ensure_ascii=False))
        while True:
            time.sleep(args.interval)
            cur = scan_projects(root, args.pattern)
            for p in diff_new(known, cur):
                _handle(p)
            known = cur
    except KeyboardInterrupt:
        print(json.dumps({"event": "bye"}, ensure_ascii=False))
    finally:
        for c in children:
            try:
                c.terminate()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
