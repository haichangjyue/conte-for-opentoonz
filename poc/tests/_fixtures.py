# SPDX-License-Identifier: BSD-3-Clause
"""测试用最小 konte 项目构造器。"""
from __future__ import annotations

import copy
from datetime import datetime, timezone


def iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def make_cut(idx, *, sec=2, frm=0, kind="standard", status="fixed", total=None):
    fps = 24
    if total is None:
        total = sec * fps + frm
    return {
        "id": f"c{idx:03d}",
        "sequenceId": "seq1",
        "scene": "EP01",
        "cut": f"C{idx:03d}",
        "number": idx,
        "order": idx,
        "duration": {"status": status, "seconds": sec if status == "fixed" else None,
                     "frames": frm if status == "fixed" else None, "totalFrames": total},
        "frame": {"kind": kind, "rect": {"x": 0, "y": 0, "w": 1920, "h": 1080}},
        "drawings": [{"id": f"c{idx}-d1", "role": "panel", "level": f"panels/C{idx:03d}.png",
                      "source": "desktop", "deviceId": None, "revision": 1, "updatedAt": iso()}],
        "action": f"action {idx}",
        "dialogue": [],
        "musicSe": [],
        "camera": {"note": "", "keyframes": []},
        "state": "final",
        "lock": None,
        "export": {"status": "notExported", "sceneFile": None},
        "revision": 1,
        "updatedAt": iso(),
    }


def make_project(n=3, *, status="final"):
    return {
        "schemaVersion": "1.0",
        "project": {
            "title": "T", "status": status, "fps": 24, "template": "tpl.psd",
            "frame": {"width": 1920, "height": 1080, "aspect": "16:9"},
            "bleed": {"left": 0, "right": 0, "top": 0, "bottom": 0},
            "cameraBox": {"x": 0, "y": 0, "w": 1920, "h": 1080},
        },
        "exportConfig": {"mode": "renderedRef", "granularity": "perCut",
                         "namingPattern": "{scene}_{cut}.tnz",
                         "onTbdDuration": "blockUntilResolved", "defaultTbdFrames": 24},
        "sequences": [{"id": "seq1", "title": "A"}],
        "cuts": [make_cut(i) for i in range(1, n + 1)],
        "meta": {"createdAt": iso(), "updatedAt": iso(), "authors": ["a"]},
    }


def clone(d):
    return copy.deepcopy(d)
