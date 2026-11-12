# SPDX-License-Identifier: BSD-3-Clause
"""Bridge 的存储/业务层：konte.json 读写、画面入库、缩略图、锁、导出任务。

以 konte.json 为单一事实源；写操作原子化（临时文件 + os.replace）；revision 乐观锁。
"""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import sys
import threading
import time
import uuid
from collections import deque
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
                 base_psd: str | None = None, hub=None,
                 token_ttl: int = 12 * 3600,
                 max_uploads_per_min: int = 60,
                 max_pair_fail: int = 5,
                 pair_fail_window: int = 60,
                 job_ttl: int = 3600,
                 max_jobs: int = 50):
        self.project_path = Path(project_path).resolve()
        self.base_psd = base_psd or os.environ.get("KONTE_BASE_PSD")
        self.hub = hub
        self.pin = pin or os.environ.get("KONTE_PIN") or f"{secrets.randbelow(1000000):06d}"
        self.tokens: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._started_at = time.time()
        # ---- 生产化参数 ----
        self.token_ttl = int(token_ttl)                 # token 有效期（秒），0/负=立即过期
        self.max_uploads_per_min = int(max_uploads_per_min)
        self.max_pair_fail = int(max_pair_fail)
        self.pair_fail_window = int(pair_fail_window)
        self.job_ttl = int(job_ttl)
        self.max_jobs = int(max_jobs)
        self._upload_times: dict[str, deque] = {}
        self._pair_fails: dict[str, deque] = {}
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
    def pair(self, pin: str, device_name: str, client: str = "") -> dict:
        now = time.time()
        with self._lock:
            # PIN 暴力尝试限制（按客户端 IP / 时间窗）
            fails = self._pair_fails.setdefault(client or "-", deque())
            while fails and now - fails[0] > self.pair_fail_window:
                fails.popleft()
            if len(fails) >= self.max_pair_fail:
                raise ApiError(429, "PAIR_LOCKED",
                               f"PIN 尝试过于频繁，请 {self.pair_fail_window}s 后重试")
            if str(pin) != str(self.pin):
                fails.append(now)
                raise ApiError(401, "BAD_PIN", "PIN 无效")
            fails.clear()
            token = secrets.token_urlsafe(24)
            device_id = "dev-" + uuid.uuid4().hex[:8]
            self.tokens[token] = {
                "deviceId": device_id, "deviceName": device_name, "at": _now(),
                "expiresAt": now + self.token_ttl,
            }
            self._prune_tokens(now)
            return {"token": token, "projectId": self.data["project"].get("title", "project"),
                    "deviceId": device_id, "expiresIn": self.token_ttl}

    def _prune_tokens(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        expired = [t for t, v in self.tokens.items() if v.get("expiresAt", 0) <= now]
        for t in expired:
            self.tokens.pop(t, None)

    def auth(self, token: str | None) -> dict:
        now = time.time()
        with self._lock:
            info = self.tokens.get(token or "")
            if not info:
                raise ApiError(401, "UNAUTHORIZED", "token 缺失或无效")
            if info.get("expiresAt", 0) <= now:
                self.tokens.pop(token, None)
                raise ApiError(401, "TOKEN_EXPIRED", "token 已过期，请重新配对")
            return info

    # ---------- 读 ----------
    def project_info(self) -> dict:
        p = self.data["project"]
        canvas = {"width": 1920, "height": 1080, "aspect": round(1920 / 1080, 4)}
        try:
            from konte_poc.template import coerce_template
            tpl = coerce_template(p.get("pdfTemplate"))
            col = tpl.columns["picture"]
            inset = int(tpl.picture.get("inset", 0))
            hs = [r.height for r in tpl.rows]
            if hs:
                w = (col.x1 - col.x0) - 2 * inset
                h = (sum(hs) / len(hs)) - 2 * inset
                if w > 0 and h > 0:
                    W = 1920
                    H = int(round(W * h / w))
                    canvas = {"width": W, "height": H, "aspect": round(w / h, 4)}
        except Exception:
            pass
        return {
            "projectId": p.get("title", "project"),
            "title": p.get("title"),
            "status": p.get("status"),
            "fps": p.get("fps"),
            "frame": p.get("frame"),
            "bleed": p.get("bleed"),
            "cameraBox": p.get("cameraBox"),
            "template": p.get("template"),
            "canvas": canvas,
        }

    def cuts_summary(self) -> list[dict]:
        out = []
        for c in sorted(self.data["cuts"], key=lambda x: x.get("order", 0)):
            layout = c.get("layout") or {}
            dur = c.get("duration") or {}
            out.append({
                "id": c["id"], "scene": c.get("scene"), "cut": c.get("cut"),
                "number": c.get("number"),
                "order": c.get("order"), "state": c.get("state"),
                "durationStatus": dur.get("status"),
                "seconds": dur.get("seconds"), "frames": dur.get("frames"),
                "totalFrames": dur.get("totalFrames"),
                "page": layout.get("page") or c.get("page"),
                "rowSpan": layout.get("rowSpan"),
                "panelCount": len(c.get("drawings", [])),
                "thumbnailUrl": f"/api/cuts/{c['id']}/thumbnail",
            })
        return out

    def get_cut(self, cut_id: str) -> dict:
        cut = self._find(cut_id)
        # 过期锁视为未锁（读时自愈）
        if self._effective_lock(cut) is None:
            cut["lock"] = None
        return cut

    def health(self) -> dict:
        with self._lock:
            now = time.time()
            self._prune_tokens(now)
            return {
                "ok": True,
                "uptimeSec": round(now - self._started_at, 1),
                "tokens": len(self.tokens),
                "jobs": len(self.jobs),
                "clients": self.hub.count() if self.hub else 0,
                "project": self.data["project"].get("title", "project"),
            }

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
                     frame_kind: str | None = None, device_id: str | None = None,
                     drawing_index: int | None = None) -> dict:
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(image_bytes))
            im.load()
        except Exception:
            raise ApiError(400, "BAD_IMAGE", "上传内容不是有效图片")
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            self._check_upload_rate(device_id)
            drawings = cut.setdefault("drawings", [])
            idx = 0 if drawing_index is None else int(drawing_index)
            if idx < 0:
                raise ApiError(400, "BAD_INDEX", "drawingIndex 不能为负")
            if idx > len(drawings):
                raise ApiError(400, "BAD_INDEX",
                               f"drawingIndex 越界：{idx}（当前 {len(drawings)} 格）")
            rev = int(cut["revision"]) + 1
            stem = f"{cut.get('scene','SC')}_{cut.get('cut','C000')}_p{idx}_r{rev}"
            drawings_dir = self.project_path.parent / "+drawings" / "konte" / stem
            drawings_dir.mkdir(parents=True, exist_ok=True)
            img_path = drawings_dir / "panel.png"
            im.convert("RGB").save(img_path, "PNG")
            level_rel = os.path.relpath(img_path, self.project_path.parent)
            if idx < len(drawings):
                drawing = drawings[idx]
            else:  # idx == len(drawings)：追加新格
                drawing = {"id": f"{cut.get('cut','C000')}-d{idx+1}", "role": "panel"}
                drawings.append(drawing)
            drawing["level"] = level_rel.replace(os.sep, "/")
            drawing["source"] = "web"
            drawing["deviceId"] = device_id
            drawing["revision"] = rev
            drawing["updatedAt"] = _now()
            if frame_kind in ("standard", "oversize"):
                cut.setdefault("frame", {})["kind"] = frame_kind
            # 多格：让 layout.rowSpan 与实际格数保持一致
            if len(drawings) > 1:
                lay = cut.setdefault("layout", {"page": cut.get("page") or 1, "rowStart": 0})
                lay["rowSpan"] = len(drawings)
            cut["revision"] = rev
            cut["updatedAt"] = _now()
            cut["export"] = {"status": "stale", "sceneFile": (cut.get("export") or {}).get("sceneFile")}
            self.data["meta"]["updatedAt"] = _now()
            self._save()
            # 缩略图（按格）
            thumb = im.convert("RGB")
            thumb.thumbnail((640, 640))
            thumb.save(self.thumb_dir / f"{cut_id}_{idx}.png", "PNG")
            if idx == 0:
                thumb.save(self.thumb_dir / f"{cut_id}.png", "PNG")
            self._emit("thumbnailReady", cutId=cut_id, revision=rev, index=idx)
            return {"drawingId": drawing["id"], "revision": rev, "index": idx,
                    "panelCount": len(drawings),
                    "thumbnailUrl": f"/api/cuts/{cut_id}/panels/{idx}/thumbnail"}

    def delete_cut(self, cut_id: str) -> dict:
        """删除一个镜头（连同其画面引用；不物理删除 +drawings 文件）。"""
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            self.data["cuts"] = [c for c in self.data["cuts"] if c["id"] != cut_id]
            self.data["meta"]["updatedAt"] = _now()
            self._save()
            self._emit("cutDeleted", cutId=cut_id)
            return {"deleted": cut_id, "cut": cut.get("cut"), "number": cut.get("number"),
                    "remaining": len(self.data["cuts"])}

    def create_panel(self, cut_id: str) -> dict:
        """给某镜头追加一个空白格子（多格镜头），返回新格索引。"""
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            idx = len(cut.get("drawings") or [])
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1920, 1080), "white").save(buf, "PNG")
        res = self.save_drawing(cut_id, buf.getvalue(), drawing_index=idx,
                                device_id="web")
        res["index"] = idx
        return res

    # ---------- 写：新建镜头 ----------
    def _next_cut_number(self) -> int:
        nums = [int(c.get("number", 0)) for c in self.data["cuts"]]
        return (max(nums) if nums else 0) + 1

    def create_cut(self, patch: dict | None = None) -> dict:
        """新建一个镜头（默认 1 格、2 秒、标准画幅），追加到项目末尾。"""
        patch = dict(patch or {})
        with self._lock:
            self._reload()
            proj = self.data["project"]
            fps = int(proj.get("fps") or 24)
            num = self._next_cut_number()
            slug = re.sub(r"[^a-z0-9]+", "", str(proj.get("title") or "scene").lower()) or "scene"
            label = str(num)  # CUT 号：1 起纯数字（不用 C001）
            cut_id = f"{slug}-c{num:03d}"
            existing = {c["id"] for c in self.data["cuts"]}
            base_id = cut_id
            k = 1
            while cut_id in existing:
                k += 1
                cut_id = f"{base_id}-{k}"
            scene = str(proj.get("title") or "SC")
            order = max([int(c.get("order", 0)) for c in self.data["cuts"]] or [0]) + 1
            seqs = self.data.get("sequences") or [{}]
            seq = patch.get("sequenceId") or seqs[0].get("id")
            pages = []
            for c in self.data["cuts"]:
                lay = c.get("layout") or {}
                p = lay.get("page") or c.get("page")
                if p:
                    pages.append(int(p))
            page = max(pages) if pages else 1
            now = _now()
            w = int(proj["frame"]["width"])
            h = int(proj["frame"]["height"])
            drawing = self._blank_drawing(scene, label)
            cut = {
                "id": cut_id, "sequenceId": seq, "scene": scene, "cut": label,
                "number": num, "order": order,
                "duration": {"status": "fixed", "seconds": 2, "frames": 0,
                             "totalFrames": 2 * fps},
                "frame": {"kind": "standard",
                          "rect": {"x": 0, "y": 0, "w": w, "h": h}},
                "drawings": [drawing],
                "action": str(patch.get("action") or ""),
                "dialogue": patch.get("dialogue") or [],
                "musicSe": patch.get("musicSe") or [],
                "audio": None,
                "camera": {"note": "", "keyframes": []},
                "state": "final", "lock": None,
                "export": {"status": "notExported", "sceneFile": None},
                "revision": 1, "updatedAt": now,
            }
            self.data["cuts"].append(cut)
            self.data["meta"]["updatedAt"] = now
            self._save()
            self._emit("cutCreated", cutId=cut_id, number=num)
            return {"cut": cut}

    def _blank_drawing(self, scene: str, label: str) -> dict:
        from PIL import Image
        stem = f"{scene}_{label}_p0_r1"
        d = self.project_path.parent / "+drawings" / "konte" / stem
        d.mkdir(parents=True, exist_ok=True)
        img = d / "panel.png"
        if not img.exists():
            Image.new("RGB", (1920, 1080), "white").save(img, "PNG")
        level = os.path.relpath(img, self.project_path.parent).replace(os.sep, "/")
        return {"id": f"{label}-d1", "role": "panel", "level": level,
                "source": "web", "deviceId": "web", "revision": 1,
                "updatedAt": _now()}


    def thumbnail_path(self, cut_id: str, index: int = 0) -> Path:
        idx = int(index)
        p = self.thumb_dir / (f"{cut_id}.png" if idx == 0 else f"{cut_id}_{idx}.png")
        if idx == 0 and not p.exists():
            alt = self.thumb_dir / f"{cut_id}_0.png"
            if alt.exists():
                p = alt
        if not p.exists():
            # 兜底：从 cut 第 idx 格的画面文件即时生成缩略图
            try:
                cut = self._find(cut_id)
                drawings = cut.get("drawings") or []
                if 0 <= idx < len(drawings):
                    from PIL import Image
                    lv = drawings[idx].get("level", "")
                    src = Path(lv)
                    if not src.is_absolute():
                        src = self.project_path.parent / src
                    if src.exists():
                        im = Image.open(src).convert("RGB")
                        im.thumbnail((640, 640))
                        self.thumb_dir.mkdir(parents=True, exist_ok=True)
                        im.save(p, "PNG")
            except Exception:
                pass
        if not p.exists():
            raise ApiError(404, "NOT_FOUND", "缩略图不存在")
        return p

    def _check_upload_rate(self, device_id: str | None) -> None:
        if not device_id:
            return
        now = time.time()
        q = self._upload_times.setdefault(device_id, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.max_uploads_per_min:
            raise ApiError(429, "RATE_LIMITED",
                           f"上传过于频繁（>{self.max_uploads_per_min}/分钟），请稍后重试")
        q.append(now)

    # ---------- 锁 ----------
    def _effective_lock(self, cut: dict) -> dict | None:
        cur = cut.get("lock")
        if not cur:
            return None
        if cur.get("ttl"):
            import datetime as _dt
            try:
                at = _dt.datetime.fromisoformat(cur["at"].replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - at).total_seconds() > cur["ttl"]:
                    return None
            except Exception:
                pass
        return cur

    def lock(self, cut_id: str, device_id: str, ttl: int = 120) -> dict:
        with self._lock:
            self._reload()
            cut = self._find(cut_id)
            cur = self._effective_lock(cut)
            if cur and cur.get("byDevice") not in (None, device_id):
                raise ApiError(409, "LOCKED", f"cut 已被 {cur.get('byDevice')} 锁定")
            cut["lock"] = {"byDevice": device_id, "at": _now(), "ttl": int(ttl)}
            self._save()
            self._emit("takeover", cutId=cut_id, byDevice=device_id, ttl=int(ttl))
            return {"locked": True, "byDevice": device_id, "ttl": int(ttl)}

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
    def _prune_jobs(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            # 过期（按结束/创建时间）
            for jid, j in list(self.jobs.items()):
                t = j.get("endedAt") or j.get("createdAt") or 0
                if j.get("status") in ("done", "failed") and now - t > self.job_ttl:
                    self.jobs.pop(jid, None)
            # 超过上限：删最旧的已结束任务
            if len(self.jobs) > self.max_jobs:
                finished = [(j.get("createdAt", 0), jid) for jid, j in self.jobs.items()
                            if j.get("status") in ("done", "failed")]
                finished.sort()
                for _, jid in finished[: len(self.jobs) - self.max_jobs]:
                    self.jobs.pop(jid, None)

    def start_export(self, targets: dict | None = None) -> str:
        # 决定稿闸门（同步快速失败 → 422）
        try:
            proj = KonteProject.load(self.project_path)
            proj.check_export_gate()
        except Exception as e:
            raise ApiError(422, "EXPORT_BLOCKED", str(e))
        self._prune_jobs()
        job_id = "job-" + uuid.uuid4().hex[:10]
        self.jobs[job_id] = {"status": "queued", "progress": 0.0, "outputs": [],
                             "error": None, "createdAt": time.time()}
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
            job.update(status="done", progress=1.0, outputs=outputs, endedAt=time.time())
            self._emit("exportProgress", jobId=job_id, status="done", progress=1.0)
        except Exception as e:  # pragma: no cover
            job.update(status="failed", error=str(e), endedAt=time.time())
            self._emit("exportProgress", jobId=job_id, status="failed", error=str(e))

    def get_job(self, job_id: str) -> dict:
        self._prune_jobs()
        if job_id not in self.jobs:
            raise ApiError(404, "NOT_FOUND", "job 不存在")
        return self.jobs[job_id]
