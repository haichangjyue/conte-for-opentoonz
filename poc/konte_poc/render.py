# SPDX-License-Identifier: BSD-3-Clause
"""画面渲染：参考图生成 + 把画面贴合进 PDF 的 PICTURE 格。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

WHITE = (255, 255, 255)


def load_panel(path: str | Path) -> Image.Image:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"画面文件不存在: {p}")
    im = Image.open(p)
    return im.convert("RGB")


def fit_contain(img: Image.Image, w: int, h: int, bg=WHITE) -> Image.Image:
    """等比缩放并居中放入 w×h 画布（留白用 bg 填充）。"""
    w, h = max(1, int(w)), max(1, int(h))
    canvas = Image.new("RGB", (w, h), bg)
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        return canvas
    scale = min(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resample = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.BICUBIC
    resized = img.resize((nw, nh), resample)
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """等比缩放并裁剪铺满 w×h（居中裁剪）。"""
    w, h = max(1, int(w)), max(1, int(h))
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resample = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.BICUBIC
    resized = img.resize((nw, nh), resample)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))


def render_reference(panel: Image.Image, frame_w: int, frame_h: int) -> Image.Image:
    """生成"成形参考图"（全分辨率，等比适配 16:9 画框）。Q8 渲染位图参考层。"""
    return fit_contain(panel, frame_w, frame_h)


def paste_picture(canvas: Image.Image, panel: Image.Image, box, *, inset: int = 8,
                  mode: str = "contain") -> None:
    """把 panel 贴合入 canvas 的 PICTURE 矩形 box=(x0,y0,x1,y1)。"""
    x0, y0, x1, y1 = box
    x0 += inset; y0 += inset; x1 -= inset; y1 -= inset
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    # 先铺白底（保持纸面视觉一致）
    canvas.paste(Image.new("RGB", (w, h), WHITE), (x0, y0))
    if mode == "cover":
        pic = fit_cover(panel, w, h)
        canvas.paste(pic, (x0, y0))
    else:
        pic = fit_contain(panel, w, h)
        canvas.paste(pic, (x0, y0))
