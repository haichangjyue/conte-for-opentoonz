# SPDX-License-Identifier: BSD-3-Clause
"""cut.layout（一个镜头跨多格 / 多画面）渲染测试。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

from PIL import Image  # noqa: E402

from konte_poc import pdfgen, template as tplmod  # noqa: E402
from konte_poc.model import KonteProject  # noqa: E402
from _fixtures import make_project  # noqa: E402


class TestLayoutSpan(unittest.TestCase):
    def test_multi_row_layout(self):
        tmp = Path(tempfile.mkdtemp(prefix="konte_span_"))
        d = make_project(3)
        d["project"]["frame"] = {"width": 320, "height": 180, "aspect": "16:9"}
        panels = tmp / "panels"
        panels.mkdir(parents=True)
        for i in range(1, 6):
            Image.new("RGB", (320, 180), (200 + i, 210, 220)).save(panels / f"p{i}.png", "PNG")
        layouts = [((0, 2), 2), ((2, 1), 1), ((3, 2), 2)]  # (rowStart, span), drawings 数
        for c, ((rs, span), nd) in zip(d["cuts"], layouts):
            c["layout"] = {"page": 1, "rowStart": rs, "rowSpan": span}
            base = c["drawings"][0]
            c["drawings"] = []
            for k in range(nd):
                dd = dict(base)
                dd["id"] = f"{c['id']}-d{k+1}"
                dd["level"] = f"panels/p{k+1}.png"
                c["drawings"].append(dd)
        p = tmp / "konte.json"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        proj = KonteProject.load(p)
        imgs, infos = pdfgen.compose_pages(proj, base_psd="")
        self.assertEqual(len(imgs), 1)
        self.assertEqual(len(infos[0]["cutIds"]), 3)
        self.assertEqual(infos[0]["pageTotalNotation"], "6+00")  # 3*48=144 -> 6s0f
        self.assertEqual(imgs[0].size, (2480, 3507))
        # 关键规则：一个 cut（无论跨几格/几张画面）只产出一个 ScenePlan（→ 一个 .tnz 工程）
        from konte_poc.export import export_project
        rep = export_project(p, tmp / "out", base_psd="", targets={"pdf": False, "scenes": True, "package": False})
        self.assertEqual(rep["cutCount"], 3)
        plans = list((tmp / "out" / "scenes").glob("*.sceneplan.json"))
        self.assertEqual(len(plans), 3)  # 3 cuts，而不是 5 张画面
        # 多帧参考层：每个 cut 的 ScenePlan.referenceImages = 该 cut 的画面数（本例 2+1+2=5）
        total_refs = 0
        for pl in plans:
            data = json.loads(pl.read_text(encoding="utf-8"))
            total_refs += len(data.get("referenceImages", []))
        self.assertEqual(total_refs, 5)
        self.assertEqual(len(list((tmp / "out" / "scenes").glob("*.ref*.png"))), 5)

    def test_schema_accepts_layout(self):
        import json as _j
        d = make_project(1)
        d["cuts"][0]["layout"] = {"page": 1, "rowStart": 0, "rowSpan": 2}
        tmp = Path(tempfile.mkdtemp(prefix="konte_span2_"))
        p = tmp / "k.json"
        p.write_text(_j.dumps(d, ensure_ascii=False), encoding="utf-8")
        KonteProject.load(p)  # 不抛即通过

    def test_distribute(self):
        from konte_poc.pdfgen import _distribute
        self.assertEqual(_distribute([1, 2], 4), [[1], [2], [], []])
        self.assertEqual(_distribute([1, 2, 3, 4, 5], 3), [[1, 2], [3, 4], [5]])
        self.assertEqual(_distribute([1, 2, 3], 1), [[1, 2, 3]])


if __name__ == "__main__":
    unittest.main()
