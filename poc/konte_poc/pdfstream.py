# SPDX-License-Identifier: BSD-3-Clause
"""流式多页 PDF 写出（零第三方依赖，逐页 Flate 无损）。

用途（P5 强化）：>200 cut 会有 40+ 页 A4；一次性把所有页图像留在内存（每页 ~26MB @300dpi）
会到 GB 级峰值。本模块按页迭代写出 PDF，任意时刻只保留 1 页位图，内存 O(1 页)。

实现：每页 = 一张 DeviceRGB 8bit 图像 XObject（/FlateDecode，zlib 无损）+ 一个内容流
把图像铺满整页 MediaBox。xref/trailer 在结尾回填。生成的 PDF 可被 pypdf/Adobe 正常解析。
"""

from __future__ import annotations

import zlib
from pathlib import Path


def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Writer:
    def __init__(self, fh):
        self.fh = fh
        self.offsets: dict[int, int] = {}

    def begin_obj(self, num: int):
        self.offsets[num] = self.fh.tell()
        self.fh.write(f"{num} 0 obj\n".encode("ascii"))

    def end_obj(self):
        self.fh.write(b"\nendobj\n")

    def write_raw(self, data: bytes):
        self.fh.write(data)


def write_pdf_streaming(images, out_path: str | Path, *, dpi: int = 300,
                        first_page_number: int | None = None) -> dict:
    """把页图像可迭代对象写成多页 PDF（逐页 Flate 无损）。

    images: 可迭代的 PIL.Image（RGB/RGBA，任意尺寸，默认同一尺寸）。
    返回 {pages, widthPt, heightPt, bytes}。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    obj_counter = 3  # 1=Catalog, 2=Pages
    kids: list[int] = []
    page_count = 0
    w_pt = h_pt = None

    with open(out_path, "wb") as fh:
        w = _Writer(fh)
        fh.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        for im in images:
            if im.mode != "RGB":
                im = im.convert("RGB")
            pw, ph = im.size
            if w_pt is None:
                w_pt = pw * 72.0 / float(dpi)
                h_pt = ph * 72.0 / float(dpi)

            page_num = obj_counter
            img_num = obj_counter + 1
            cont_num = obj_counter + 2
            obj_counter += 3
            page_count += 1

            # ---- 图像 XObject（Flate 无损）----
            raw = im.tobytes()
            comp = zlib.compress(raw, 6)
            w.begin_obj(img_num)
            w.write_raw(
                f"<< /Type /XObject /Subtype /Image /Width {pw} /Height {ph} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                f"/Length {len(comp)} >>\nstream\n".encode("ascii"))
            w.write_raw(comp)
            w.write_raw(b"\nendstream")
            w.end_obj()

            # ---- 内容流：把图像铺满整页 ----
            content = (f"q\n{w_pt:.4f} 0 0 {h_pt:.4f} 0 0 cm\n/Im0 Do\nQ\n").encode("ascii")
            w.begin_obj(cont_num)
            w.write_raw(f"<< /Length {len(content)} >>\nstream\n".encode("ascii"))
            w.write_raw(content)
            w.write_raw(b"\nendstream")
            w.end_obj()

            # ---- 页对象 ----
            w.begin_obj(page_num)
            w.write_raw(
                (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.4f} {h_pt:.4f}] "
                 f"/Resources << /XObject << /Im0 {img_num} 0 R >> >> "
                 f"/Contents {cont_num} 0 R >>").encode("ascii"))
            w.end_obj()
            kids.append(page_num)

        # ---- Pages ----
        kids_ref = " ".join(f"{k} 0 R" for k in kids)
        w.begin_obj(2)
        w.write_raw(f"<< /Type /Pages /Kids [{kids_ref}] /Count {page_count} >>".encode("ascii"))
        w.end_obj()
        # ---- Catalog ----
        w.begin_obj(1)
        w.write_raw(b"<< /Type /Catalog /Pages 2 0 R >>")
        w.end_obj()

        # ---- xref ----
        total = obj_counter - 1  # 最大对象号
        xref_off = fh.tell()
        fh.write(f"xref\n0 {total + 1}\n".encode("ascii"))
        fh.write(b"0000000000 65535 f \n")
        for num in range(1, total + 1):
            off = w.offsets.get(num, 0)
            fh.write(f"{off:010d} 00000 n \n".encode("ascii"))
        fh.write(
            (f"trailer\n<< /Size {total + 1} /Root 1 0 R >>\nstartxref\n{xref_off}\n%%EOF\n")
            .encode("ascii"))

    return {"pages": page_count,
            "widthPt": round(w_pt or 0, 2), "heightPt": round(h_pt or 0, 2),
            "bytes": out_path.stat().st_size}
