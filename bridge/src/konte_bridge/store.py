# SPDX-License-Identifier: BSD-3-Clause
"""Bridge 的存储/业务层：konte.json 读写、画面入库、缩略图、锁、导出任务。

以 konte.json 为单一事实源；写操作原子化（临时文件 + os.replace）；revision 乐观锁。
"""

from __future__ import annotations

import io
import json
import os
import secrets
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from konte_poc import export as export_mod
    from konte_poc.model import KonteProject
except Exception:  # pragma: no cover - 允许直接以路径运行
    _repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(_repo / "poc"))
    from konte_poc import export as export_mod
    from konte_poc.model import KonteProject


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, project_path: str | Path, *, pin: str | None = None,
                 base_psd: str | None = None, hub=None):
        self.project_path = Path(project_path).resolve()
        self.base_psd = base_psd or os.environ.get("KONTE_BASE_PSD")
        self.hub = hub
        self.pin = pin or os.environ.get("KONTE_PIN") or f"{secrets.randbelow(1000000):06d}"
        self.tokens: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self._lock = threading.RLock()
        self.thumb_dir = self.project_path.parent / ".bridge" / "thumbs"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.data = self._read()

    # ---------- 基础 IO ----------
    def _read(self) -> dict:
        with open(self.project_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        tmp = self.project_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.project_path)

    def _reload(self) -> None:
        self.data = self._read()

    def _emit(self, event: str, **kw) -> None:
        if self.hub:
            payload = {"event": event, **kw}
            self.hub.broadcast(json.dumps(payload, ensure_ascii=False))

    def _find(self, cut_id: str) -> dict:
        for c in self.data["cuts"]:
            if c["id"] == cut_id:
                return c
        raise ApiError(404, "NOT_FOUND", f"cut 不存在: {cut_id}")

    # ---------- 配对 / 鉴权 ----------
    def pair(self, pin: str, device_name: str) -> dict:
        if str(pin) != str(self.pin):
            raise ApiError(401, "BAD_PIN", "PIN 无效")
        token = secrets.token_urlsafe(24)
        device_id = "dev-" + uuid.uuid4().hex[:8]
        self.tokens[token] = {"deviceId": device_id, "deviceName": device_name, "at": _now()}
        return {"token": token, "projectId": self.data["project"].get("title", "project"),
                "deviceId": device_id}

    def auth(self, token: str | None) -> dict:
        if not token or token not in self.tokens:
            raise ApiError(401, "UNAUTHORIZED", "token 缺失或无效")
        return self.tokens[token]

    # ---------- 读 ----------
    def project_info(self) -> dict:
        p = self.data["project"]
        return {
            "projectId": p.get("title", "project"),
            "title": p.get("title"),
            "status": p.get("status"),
            "fps": p.get("fps"),
            "frame": p.get("frame"),
            "bleed": p.get("bleed"),
            "cameraBox": p.get("cameraBox"),
            "template": p.get("template"),
        }

    def cuts_summary(self) -> list[dict]:
        out = []
        for c in sorted(self.data["cuts"], key=lambda x: x.get("order", 0)):
            out.append({
                "id": c["id"], "scene": c.get("scene"), "cut": c.get("cut"),
                "order": c.get("order"), "state": c.get("state"),
                "durationStatus": c["duration"]["status"],
                "thumbnailUrl": f"/api/cuts/{c['id']}/thumbnail",
            })
        return out

    def get_cut(self, cut_id: str) -> dict:
        return self._find(cut_id)

    # ---------- 写：cut 元数据 ----------
    UPDATABLE = {"action", "dialogue", "musicSe", "duration", "frame", "camera", "state", "sequenceId"}

    def update_cut(self, cut_id: str, patch: dict) -> dict:
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            expected = patch.pop("expectedRevision", None)
            if expected is not None and int(expected) != int(cut["revision"]):
                raise ApiError(409, "REVISION_CONFLICT",
                               f"revision 冲突：期望 {expected}，实际 {cut['revision']}")
            for k, v in patch.items():
                if k not in self.UPDATABLE:
                    raise ApiError(400, "BAD_FIELD", f"字段不可改: {k}")
                cut[k] = v
            cut["revision"] = int(cut["revision"]) + 1
            cut["updatedAt"] = _now()
            self.data["meta"]["updatedAt"] = _now()
            self._save()
            self._emit("cutUpdated", cutId=cut_id, revision=cut["revision"])
            return {"revision": cut["revision"]}

    # ---------- 写：画面入库 ----------
    def save_drawing(self, cut_id: str, image_bytes: bytes, *,
                     frame_kind: str | None = None, device_id: str | None = None) -> dict:
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(image_bytes))
            im.load()
        except Exception:
            raise ApiError(400, "BAD_IMAGE", "上传内容不是有效图片")
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            rev = int(cut["revision"]) + 1
            stem = f"{cut.get('scene','SC')}_{cut.get('cut','C000')}_r{rev}"
            drawings_dir = self.project_path.parent / "+drawings" / "konte" / stem
            drawings_dir.mkdir(parents=True, exist_ok=True)
            img_path = drawings_dir / "panel.png"
            im.convert("RGB").save(img_path, "PNG")
            level_rel = os.path.relpath(img_path, self.project_path.parent)
            drawing = cut["drawings"][0]
            drawing["level"] = level_rel.replace(os.sep, "/")
            drawing["source"] = "web"
            drawing["deviceId"] = device_id
            drawing["revision"] = rev
            drawing["updatedAt"] = _now()
            if frame_kind in ("standard", "oversize"):
                cut["frame"]["kind"] = frame_kind
            cut["revision"] = rev
            cut["updatedAt"] = _now()
            self._save()
            # 缩略图
            thumb = im.convert("RGB")
            thumb.thumbnail((640, 640))
            thumb.save(self.thumb_dir / f"{cut_id}.png", "PNG")
            self._emit("thumbnailReady", cutId=cut_id, revision=rev)
            return {"drawingId": drawing["id"], "revision": rev,
                    "thumbnailUrl": f"/api/cuts/{cut_id}/thumbnail"}

    def thumbnail_path(self, cut_id: str) -> Path:
        p = self.thumb_dir / f"{cut_id}.png"
        if not p.exists():
            raise ApiError(404, "NOT_FOUND", "缩略图不存在")
        return p

    # ---------- 锁 ----------
    def lock(self, cut_id: str, device_id: str, ttl: int = 120) -> dict:
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            cur = cut.get("lock")
            if cur and cur.get("ttl"):
                import datetime as _dt
                try:
                    at = _dt.datetime.fromisoformat(cur["at"].replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - at).total_seconds() > cur["ttl"]:
                        cur = None
                except Exception:
                    pass
            if cur and cur.get("byDevice") not in (None, device_id):
                raise ApiError(409, "LOCKED", f"cut 已被 {cur.get('byDevice')} 锁定")
            cut["lock"] = {"byDevice": device_id, "at": _now(), "ttl": ttl}
            self._save()
            self._emit("takeover", cutId=cut_id, byDevice=device_id)
            return {"locked": True, "byDevice": device_id}

    def unlock(self, cut_id: str, device_id: str | None = None) -> dict:
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            cur = cut.get("lock")
            if cur and device_id and cur.get("byDevice") not in (None, device_id):
                raise ApiError(409, "LOCKED", "非持锁设备")
            cut["lock"] = None
            self._save()
            return {"locked": False}

    # ---------- 导出任务 ----------
    def start_export(self, targets: dict | None = None) -> str:
        # 决定稿闸门（同步快速失败 → 422）
        try:
            proj = KonteProject.load(self.project_path)
            proj.check_export_gate()
        except Exception as e:
            raise ApiError(422, "EXPORT_BLOCKED", str(e))
        job_id = "job-" + uuid.uuid4().hex[:10]
        self.jobs[job_id] = {"status": "queued", "progress": 0.0, "outputs": [], "error": None}
        out_dir = self.project_path.parent / "deliverable" / self.data["project"].get("title", "out")
        t = threading.Thread(target=self._run_export, args=(job_id, out_dir, targets), daemon=True)
        t.start()
        return job_id

    def _run_export(self, job_id: str, out_dir: Path, targets: dict | None):
        job = self.jobs[job_id]
        try:
            job["status"] = "running"; job["progress"] = 0.1
            self._emit("exportProgress", jobId=job_id, status="running", progress=0.1)
            report = export_mod.export_project(self.project_path, out_dir,
                                               base_psd=self.base_psd, targets=targets)
            outputs = [str(out_dir / "storyboard.pdf"), str(out_dir / "manifest.json")]
            job.update(status="done", progress=1.0, outputs=outputs)
            self._emit("exportProgress", jobId=job_id, status="done", progress=1.0)
        except Exception as e:  # pragma: no cover
            job.update(status="failed", error=str(e))
            self._emit("exportProgress", jobId=job_id, status="failed", error=str(e))

    def get_job(self, job_id: str) -> dict:
        if job_id not in self.jobs:
            raise ApiError(404, "NOT_FOUND", "job 不存在")
        return self.jobs[job_id]
