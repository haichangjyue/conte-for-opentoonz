# SPDX-License-Identifier: BSD-3-Clause
"""ScenePlan —— 每个 cut 的 .tnz 生成"输入契约"。

真正的 .tnz 由 OpenToonz C++ 导出内核按本计划生成（见 KERNEL_CONTRACT.md）。
Python PoC 负责把 konte.json 归一成与 OT 无关、可序列化、可逐个校验的 ScenePlan。
"""

from __future__ import annotations

from pathlib import Path

from .model import KonteProject


def _resolve_audio(project: KonteProject, cut: dict):
    audio = cut.get("audio")
    if not audio or not audio.get("path"):
        return None
    p = Path(audio["path"])
    if not p.is_absolute():
        p = project.base_dir / p
    return {"path": str(p.resolve())}


def scene_filename(project: KonteProject, cut: dict) -> str:
    pattern = project.export_config.get("namingPattern", "{scene}_{cut}.tnz")
    return pattern.format(scene=cut.get("scene", "SC"), cut=cut.get("cut", "C000"))


def build_scene_plan(project: KonteProject, cut: dict) -> dict:
    fps = project.fps
    total = project.total_frames(cut)
    dur = cut["duration"]
    sec, frm = (dur.get("seconds"), dur.get("frames"))
    if sec is None or frm is None:
        sec, frm = divmod(total, fps)
    frame = cut.get("frame", {})
    fname = scene_filename(project, cut)
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
        # 参考层（Q8：渲染位图参考层，锁定不可编辑）
        "referenceImage": f"scenes/{fname.replace('.tnz', '')}.ref.png",
        "level": {
            "type": "raster",
            "path": f"scenes/{fname.replace('.tnz', '')}.ref.png",
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
        "sound": _resolve_audio(project, cut),
        "sequenceId": cut.get("sequenceId"),
    }
