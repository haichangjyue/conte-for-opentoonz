# SPDX-License-Identifier: BSD-3-Clause
"""manifest.json 生成（导出产物清单，契约见 konte-format/manifest.schema.json）。"""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_manifest(
    *,
    project_id: str,
    fps: int,
    template: str | None,
    items: list[dict],
    sequences: list[dict] | None = None,
    pdf: str | None = None,
    package_dir: str | None = None,
    generated_at: str | None = None,
) -> dict:
    return {
        "projectId": project_id,
        "generatedAt": generated_at or now_iso(),
        "fps": fps,
        "template": template,
        "items": items,
        "sequences": sequences or [],
        "pdf": pdf,
        "packageDir": package_dir,
    }
