# SPDX-License-Identifier: BSD-3-Clause
"""ScenePlan —— 每个 cut 的 .tnz 生成"输入契约"。

真正的 .tnz 由 OpenToonz C++ 导出内核按本计划生成（见 KERNEL_CONTRACT.md）。
Python PoC 负责把 konte.json 归一成与 OT 无关、可序列化、可逐个校验的 ScenePlan。
"""

from __future__ import annotations

import re
import wave
from pathlib import Path

from .model import KonteProject


def _resolve_audio(project: KonteProject, cut: dict):
    audio = cut.get("audio")
    if not audio or not audio.get("path"):
        return None
    p = Path(audio["path"])
    if not p.is_absolute():
        p = project.base_dir / p
    return {"path": str(p.resolve()), "offsetFrames": int(audio.get("offsetFrames", 0) or 0)}


def audio_info(path: str | Path | None) -> dict:
    """读取 wav 基本信息（用于 manifest 音频字段）。失败返回空。"""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {"exists": False}
    info = {"exists": True, "bytes": p.stat().st_size}
    try:
        with wave.open(str(p), "rb") as w:
            rate = w.getframerate()
            frames = w.getnframes()
            info.update(sampleRate=rate, channels=w.getnchannels(),
                        sampleWidth=w.getsampwidth(), frames=frames,
                        durationSec=round(frames / float(rate or 1), 3))
    except Exception:
        pass
    return info


def cut_number(cut: dict) -> int | None:
    """取镜头号（1 基）。优先 number；否则从 cut 文本（如 "C001"/"001"/"1"）解析。"""
    n = cut.get("number")
    if isinstance(n, (int, float)) and int(n) > 0:
        return int(n)
    m = re.search(r"(\d+)", str(cut.get("cut", "")) or "")
    return int(m.group(1)) if m else None


def scene_filename(project: KonteProject, cut: dict) -> str:
    """导出 .tnz 文件名：`[项目名称]_[镜头号 3 位]`，例如 `EP01_001.tnz`。"""
    proj_title = str(project.data.get("project", {}).get("title")
                     or cut.get("scene") or "SC")
    n = cut_number(cut)
    if n is not None:
        return f"{proj_title}_{n:03d}.tnz"
    pattern = project.export_config.get("namingPattern", "{scene}_{cut}.tnz")
    return pattern.format(scene=cut.get("scene", "SC"), cut=cut.get("cut", "C000"))


def build_scene_plan(project: KonteProject, cut: dict, *, include_audio: bool = True,
                     reference_images: list[str] | None = None) -> dict:
    fps = project.fps
    total = project.total_frames(cut)
    dur = cut["duration"]
    sec, frm = (dur.get("seconds"), dur.get("frames"))
    if sec is None or frm is None:
        sec, frm = divmod(total, fps)
    frame = cut.get("frame", {})
    fname = scene_filename(project, cut)
    ref_base = f"scenes/{fname.replace('.tnz', '')}.ref.png"
    refs = reference_images or [ref_base]
    return {
        "cutId": cut["id"],
        "scene": cut.get("scene"),
        "cut": cut.get("cut"),
        "number": cut.get("number"),
        "order": cut.get("order"),
        "sceneFile": fname,
        "fps": fps,
        "duration": {
            "status": dur["status"],
            "seconds": sec,
            "frames": frm,
            "totalFrames": total,
            "durationSec": total / float(fps),
        },
        # 参考层（Q8：渲染位图参考层，锁定不可编辑；多帧参考层 = 该 cut 的多张画面）
        "referenceImage": refs[0],
        "referenceImages": refs,
        "level": {
            "type": "raster",
            "path": ref_base,
            "lock": True,
        },
        # 时长钉定：参考层从第 1 帧 hold 到第 N 帧 → TXsheet 帧数 = N
        "holdFrames": {"from": 1, "to": total},
        # 文字进 Note 列
        "noteColumns": {
            "action": cut.get("action", ""),
            "dialogue": cut.get("dialogue", []),
            "musicSe": cut.get("musicSe", []),
        },
        # 画面画幅（超框/bleed）
        "frame": {
            "kind": frame.get("kind", "standard"),
            "rect": frame.get("rect"),
            "cameraBox": project.project.get("cameraBox"),
        },
        "camera": cut.get("camera", {"note": "", "keyframes": []}),
        "sound": _resolve_audio(project, cut) if include_audio else None,
        "sequenceId": cut.get("sequenceId"),
    }
