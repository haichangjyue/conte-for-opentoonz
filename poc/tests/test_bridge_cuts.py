# SPDX-License-Identifier: BSD-3-Clause
"""Bridge 新建镜头 / 一镜多格（多 drawing）单元测试。"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_POC))
sys.path.insert(0, str(_POC.parent / "bridge" / "src"))

from PIL import Image  # noqa: E402

from konte_bridge.store import Store  # noqa: E402


def _png(color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(buf, "PNG")
    return buf.getvalue()


class BridgeCutsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "EP01"
        src = _POC / "examples" / "EP01"
        if not (src / "konte.json").exists():
            self.skipTest("缺少 EP01 示例")
        shutil.copytree(src, self.dir)
        self.project = self.dir / "konte.json"
        self.store = Store(self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def _n(self):
        import json
        return len(json.loads(self.project.read_text(encoding="utf-8"))["cuts"])

    def test_create_cut_appends_valid_cut(self):
        n0 = self._n()
        res = self.store.create_cut({})
        cut = res["cut"]
        self.assertEqual(self._n(), n0 + 1)
        self.assertEqual(cut["number"], n0 + 1)
        self.assertEqual(len(cut["drawings"]), 1)
        self.assertTrue((self.dir / cut["drawings"][0]["level"]).exists(),
                        "新建镜头应生成空白画面文件")
        # 单格新镜头不设 layout（按普通分页排版）；加格后才产生 layout
        self.assertNotIn("layout", cut)
        for k in ("id", "scene", "cut", "number", "order", "duration", "frame",
                  "drawings", "action", "dialogue", "musicSe", "camera", "state",
                  "export", "revision", "updatedAt"):
            self.assertIn(k, cut)

    def test_create_panel_and_multi_cell_edit(self):
        cut = self.store.create_cut({})["cut"]
        cid = cut["id"]
        # 追加第 2 格
        res = self.store.create_panel(cid)
        self.assertEqual(res["index"], 1)
        cur = self.store.get_cut(cid)
        self.assertEqual(len(cur["drawings"]), 2)
        self.assertEqual(cur["layout"]["rowSpan"], 2)
        # 编辑第 2 格（红色）
        r = self.store.save_drawing(cid, _png((10, 200, 10)), drawing_index=1, device_id="t")
        self.assertEqual(r["index"], 1)
        cur = self.store.get_cut(cid)
        self.assertEqual(len(cur["drawings"]), 2, "编辑已有格不应新增")
        self.assertEqual(cur["drawings"][1]["level"], cur["drawings"][1]["level"])
        # 两格缩略图都可取
        self.assertTrue(self.store.thumbnail_path(cid, 0).exists())
        self.assertTrue(self.store.thumbnail_path(cid, 1).exists())
        # 第 2 格像素应是绿色（验证写入到正确格）
        im = Image.open(self.dir / cur["drawings"][1]["level"])
        px = im.convert("RGB").getpixel((5, 5))
        self.assertGreater(px[1], px[0], "第 2 格应写入绿色图像")

    def test_save_drawing_append_on_index_len(self):
        cut = self.store.create_cut({})["cut"]
        cid = cut["id"]
        # drawing_index == 现有格数 → 追加
        r = self.store.save_drawing(cid, _png((0, 0, 200)), drawing_index=1, device_id="t")
        self.assertEqual(r["index"], 1)
        self.assertEqual(len(self.store.get_cut(cid)["drawings"]), 2)

    def test_delete_cut(self):
        n0 = self._n()
        cut = self.store.create_cut({})["cut"]
        self.assertEqual(self._n(), n0 + 1)
        res = self.store.delete_cut(cut["id"])
        self.assertEqual(res["deleted"], cut["id"])
        self.assertEqual(self._n(), n0)
        with self.assertRaises(Exception):
            self.store.get_cut(cut["id"])

    def test_bad_index_rejected(self):
        cut = self.store.create_cut({})["cut"]
        with self.assertRaises(Exception):
            self.store.save_drawing(cut["id"], _png(), drawing_index=5, device_id="t")

    def test_http_routes_create_cut_and_panel(self):
        import json
        import threading
        import urllib.request

        from konte_bridge.server import create_server

        httpd = create_server(self.project, host="127.0.0.1", port=0, pin="111111")
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        base = f"http://127.0.0.1:{port}"

        def _req(path, method="GET", body=None, token=None):
            data = json.dumps(body).encode() if body is not None else None
            headers = {}
            if data is not None:
                headers["Content-Type"] = "application/json"
            if token:
                headers["Authorization"] = "Bearer " + token
            req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read(), r.headers.get("Content-Type")

        try:
            st, raw, _ = _req("/api/pair", "POST", {"pin": "111111", "deviceName": "t"})
            token = json.loads(raw)["token"]
            st, raw, _ = _req("/api/cuts", "POST", {}, token)
            self.assertEqual(st, 201)
            cut = json.loads(raw)["cut"]
            st, raw, _ = _req(f"/api/cuts/{cut['id']}/panels", "POST", {}, token)
            self.assertEqual(st, 201)
            self.assertEqual(json.loads(raw)["index"], 1)
            st, raw, ctype = _req(f"/api/cuts/{cut['id']}/panels/1/thumbnail", "GET", None, token)
            self.assertEqual(st, 200)
            self.assertIn("image/png", ctype)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
