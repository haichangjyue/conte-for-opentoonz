# SPDX-License-Identifier: BSD-3-Clause
"""生成示例项目 examples/EP01（konte.json + 模拟分镜画面 PNG）。

用途：无需美术素材即可跑通导出（PDF/参考图/manifest）。
真实项目将 panels/ 换成导演手绘/平板回灌的 PNG。

用法：python tools/make_demo.py [输出目录]
"""

from __future__ import annotations

import json
import math
import struct
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
POC = HERE.parent
sys.path.insert(0, str(POC))

from PIL import Image, ImageDraw  # noqa: E402

from konte_poc import textfit  # noqa: E402

FPS = 24
FRAME_W, FRAME_H = 1920, 1080


def _iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _panel(path: Path, cut_label: str, title: str, w: int, h: int, seed: int) -> None:
    bg = (247, 244, 236)
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    ink = (35, 35, 40)
    # 外框
    d.rectangle([6, 6, w - 7, h - 7], outline=ink, width=5)
    # 地平线 / 透视辅助
    d.line([0, int(h * 0.62), w, int(h * 0.62)], fill=(120, 120, 120), width=3)
    # 角色（圆头 + 身体 + 手臂）
    cx = int(w * (0.32 + 0.07 * (seed % 3)))
    cy = int(h * 0.40)
    r = int(h * 0.12)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ink, width=5)
    d.line([cx, cy + r, cx, cy + int(r * 2.6)], fill=ink, width=5)
    d.line([cx, cy + int(r * 1.3), cx - int(r * 1.3), cy + int(r * 2.2)], fill=ink, width=5)
    d.line([cx, cy + int(r * 1.3), cx + int(r * 1.4), cy + int(r * 1.9)], fill=ink, width=5)
    d.line([cx, cy + int(r * 2.6), cx - int(r * 0.9), cy + int(r * 3.6)], fill=ink, width=5)
    d.line([cx, cy + int(r * 2.6), cx + int(r * 0.9), cy + int(r * 3.6)], fill=ink, width=5)
    # 背景建筑/山（简单折线）
    pts = []
    for i in range(0, w + 60, 60):
        yy = int(h * 0.62 - 40 - 30 * math.sin(i * 0.02 + seed))
        pts.append((i, yy))
    d.line(pts, fill=(90, 90, 90), width=3)
    # 标注
    f1 = textfit.get_font(max(28, h // 22), bold=True)
    f2 = textfit.get_font(max(18, h // 40))
    d.text((20, 16), cut_label, font=f1, fill=(150, 20, 20))
    d.text((20, 16 + max(34, h // 20)), title, font=f2, fill=(60, 60, 120))
    # 角落注记（模拟运镜/注意）
    d.text((w - 360, h - 60), "CAM: 固定 / 参考", font=f2, fill=(80, 80, 80))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG")


def _wav(path: Path, seconds: float, freq: float) -> None:
    """生成一段简单提示音 WAV（用于演示“带音轨”的导出）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    n = max(1, int(seconds * rate))
    fade = max(1, int(0.05 * rate))
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for k in range(n):
            env = min(1.0, k / fade, (n - k) / fade)
            # 轻微颤音，听感更像“对白提示”
            f = freq * (1.0 + 0.02 * math.sin(2 * math.pi * 3.0 * k / rate))
            v = int(10000 * env * math.sin(2 * math.pi * f * k / rate))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


def make(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    panels = out / "panels"
    panels.mkdir(exist_ok=True)

    # (cut, title, seconds, frames, kind, panel_size)
    spec = [
        ("C001", "A-part 开场：城市远景", 3, 0, "standard", (FRAME_W, FRAME_H)),
        ("C002", "主角入门（中景）", 1, 12, "standard", (FRAME_W, FRAME_H)),
        ("C003", "对话：反应镜头", 2, 0, "standard", (FRAME_W, FRAME_H)),
        ("C004", "横摇（超框 bleed）", 0, 18, "oversize", (2400, 1080)),
        ("C005", "奔跑（远景）", 4, 6, "standard", (FRAME_W, FRAME_H)),
        ("C006", "特写：眼神", 2, 12, "standard", (FRAME_W, FRAME_H)),
        ("C007", "转场：天空空镜", 3, 0, "standard", (FRAME_W, FRAME_H)),
    ]

    cuts = []
    for i, (cut, title, sec, frm, kind, (pw, ph)) in enumerate(spec):
        _panel(panels / f"{cut}.png", cut, title, pw, ph, seed=i)
        dur_sec = (sec * FPS + frm) / float(FPS)
        _wav(out / "audio" / f"{cut}.wav", dur_sec, 220.0 + 40.0 * i)
        rect = {"x": 0, "y": 0, "w": FRAME_W, "h": FRAME_H}
        if kind == "oversize":
            rect = {"x": -240, "y": 0, "w": FRAME_W + 480, "h": FRAME_H}
        cuts.append({
            "id": f"ep01-{cut.lower()}",
            "sequenceId": "seq1",
            "scene": "EP01",
            "cut": cut,
            "number": i + 1,
            "order": i + 1,
            "duration": {
                "status": "fixed",
                "seconds": sec,
                "frames": frm,
                "totalFrames": sec * FPS + frm,
            },
            "frame": {"kind": kind, "rect": rect},
            "drawings": [{
                "id": f"{cut}-d1",
                "role": "panel",
                "level": f"panels/{cut}.png",
                "source": "desktop",
                "deviceId": "desk-main",
                "revision": 1,
                "updatedAt": _iso(),
            }],
            "action": f"{title}。カメラ固定。角色の動きに合わせて間を取る。",
            "dialogue": [
                {"character": "AKIRA", "text": "……行くぞ。", "offscreen": False},
            ] if i % 2 == 0 else [],
            "musicSe": [{"text": "SE: 足音", "atFrame": 0}] if i == 4 else [],
            "audio": {"path": f"audio/{cut}.wav"},
            "camera": {"note": "固定" if kind == "standard" else "横摇（超框 bleed）", "keyframes": []},
            "state": "final",
            "lock": None,
            "export": {"status": "notExported", "sceneFile": None},
            "revision": 1,
            "updatedAt": _iso(),
        })

    project = {
        "schemaVersion": "1.0",
        "project": {
            "title": "EP01",
            "status": "final",
            "fps": FPS,
            "template": "scfilms_StoryBoard.psd",
            "frame": {"width": FRAME_W, "height": FRAME_H, "aspect": "16:9"},
            "bleed": {"left": 0, "right": 0, "top": 0, "bottom": 0},
            "cameraBox": {"x": 0, "y": 0, "w": FRAME_W, "h": FRAME_H},
        },
        "exportConfig": {
            "mode": "renderedRef",
            "granularity": "perCut",
            "namingPattern": "{scene}_{cut}.tnz",
            "onTbdDuration": "blockUntilResolved",
            "defaultTbdFrames": 24,
        },
        "sequences": [{"id": "seq1", "title": "A Part"}],
        "cuts": cuts,
        "meta": {"createdAt": _iso(), "updatedAt": _iso(), "authors": ["Director"]},
    }

    proj_path = out / "konte.json"
    proj_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(proj_path)
    return proj_path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else POC / "examples" / "EP01"
    make(target)
