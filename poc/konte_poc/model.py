# SPDX-License-Identifier: BSD-3-Clause
"""konte 数据模型：加载 / 校验 / 不变量 / 决定稿闸门 / 时长换算 / 寻址。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import minischema
from .errors import ExportGateError, InvariantError, SchemaError

# konte-format/konte.schema.json 相对本包的位置：poc/konte_poc -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = _REPO_ROOT / "konte-format" / "konte.schema.json"


def load_schema(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else DEFAULT_SCHEMA_PATH
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class KonteProject:
    data: dict
    base_dir: Path
    schema: dict

    # ---------- 载入 ----------
    @classmethod
    def load(cls, path: str | os.PathLike, schema_path: str | os.PathLike | None = None) -> "KonteProject":
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        proj = cls(data=data, base_dir=p.parent, schema=load_schema(schema_path))
        proj.validate_schema()
        proj.validate_invariants()
        return proj

    # ---------- 校验 ----------
    def validate_schema(self) -> None:
        errs = minischema.validate(self.data, self.schema)
        if errs:
            raise SchemaError(errs)

    def validate_invariants(self) -> None:
        proj = self.data["project"]
        fps = proj["fps"]
        errors: list[str] = []
        for cut in self.data["cuts"]:
            cid = cut.get("id", "?")
            dur = cut["duration"]
            if dur["status"] == "fixed":
                if dur.get("seconds") is None or dur.get("frames") is None:
                    errors.append(f"cut {cid}: fixed 时长需要 seconds 与 frames")
                else:
                    expect = dur["seconds"] * fps + dur["frames"]
                    if dur["totalFrames"] != expect:
                        errors.append(
                            f"cut {cid}: totalFrames={dur['totalFrames']} != seconds*fps+frames={expect}"
                        )
            if len(cut.get("drawings", [])) < 1:
                errors.append(f"cut {cid}: 至少需要 1 个 drawing")
            if cut.get("revision", 0) < 1:
                errors.append(f"cut {cid}: revision 必须 >= 1")
        if errors:
            raise InvariantError("; ".join(errors))

    # ---------- 便捷访问 ----------
    @property
    def project(self) -> dict:
        return self.data["project"]

    @property
    def fps(self) -> int:
        return int(self.data["project"]["fps"])

    @property
    def status(self) -> str:
        return self.data["project"]["status"]

    @property
    def export_config(self) -> dict:
        return self.data["exportConfig"]

    def sorted_cuts(self) -> list[dict]:
        return sorted(self.data["cuts"], key=lambda c: (c.get("order", 0), c.get("number", 0)))

    def get_cut(self, cut_id: str) -> dict:
        for c in self.data["cuts"]:
            if c["id"] == cut_id:
                return c
        raise KeyError(cut_id)

    # ---------- 时长 ----------
    def total_frames(self, cut: dict) -> int:
        """返回该 cut 的帧数。tbd 时按配置处理。"""
        dur = cut["duration"]
        if dur["status"] in ("fixed", "default"):
            return int(dur["totalFrames"])
        if dur["status"] == "tbd":
            if self.export_config.get("onTbdDuration", "blockUntilResolved") == "defaultWithWarning":
                return int(self.export_config.get("defaultTbdFrames", 24))
            raise ExportGateError(f"cut {cut['id']} 时长为 TBD，未解决前不可导出")
        raise InvariantError(f"cut {cut['id']} 未知 duration.status={dur['status']!r}")

    def duration_sec(self, cut: dict) -> float:
        return self.total_frames(cut) / float(self.fps)

    # ---------- 决定稿闸门 ----------
    def check_export_gate(self) -> None:
        details: list[str] = []
        if self.status != "final":
            details.append(f"project.status={self.status!r}，需为 'final'（决定稿已锁定）")
        on_tbd = self.export_config.get("onTbdDuration", "blockUntilResolved")
        for cut in self.sorted_cuts():
            if cut["duration"]["status"] == "tbd" and on_tbd == "blockUntilResolved":
                details.append(f"cut {cut['id']}（{cut.get('scene','')} {cut.get('cut','')}）时长仍为 TBD")
        if details:
            raise ExportGateError("决定稿闸门未通过：不得导出", details)

    # ---------- 画面寻址 ----------
    def resolve_drawing(self, cut: dict, drawing: dict) -> Path:
        p = Path(drawing["level"])
        return p if p.is_absolute() else (self.base_dir / p)

    def resolve_level(self, cut: dict) -> Path:
        if not cut.get("drawings"):
            raise InvariantError(f"cut {cut['id']} 没有画面")
        return self.resolve_drawing(cut, cut["drawings"][0])

    # ---------- 分页（每页 5 cut） ----------
    def page_of(self, cut: dict, per_page: int = 5) -> int:
        layout = cut.get("layout") or {}
        if layout.get("page"):
            return int(layout["page"])
        if "page" in cut and cut["page"]:
            return int(cut["page"])
        idx = self.sorted_cuts().index(cut)
        return idx // per_page + 1
