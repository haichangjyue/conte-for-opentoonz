# SPDX-License-Identifier: BSD-3-Clause
"""画面渲染：参考图生成 + 把画面贴合进 PDF 的 PICTURE 格（含超框/bleed 策略）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

WHITE = (255, 255, 255)

# 超框 bleed 提示色（浅蓝）
_BLEED_COLOR = (70, 120, 200)


def load_panel(path: str | Path) -> Image.Image:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"画面文件不存在: {p}")
    with Image.open(p) as im:
        return im.convert("RGB")


def _resample():
    return Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.BICUBIC


def fit_contain(img: Image.Image, w: int, h: int, bg=WHITE) -> Image.Image:
    """等比缩放并居中放入 w×h 画布（留白用 bg 填充）。"""
    w, h = max(1, int(w)), max(1, int(h))
    canvas = Image.new("RGB", (w, h), bg)
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        return canvas
    scale = min(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resized = img.resize((nw, nh), _resample())
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """等比缩放并居中裁剪铺满 w×h（cover）。"""
    w, h = max(1, int(w)), max(1, int(h))
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resized = img.resize((nw, nh), _resample())
    left = (nw - w) // 2
    top = (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))


def render_reference(panel: Image.Image, frame_w: int, frame_h: int) -> Image.Image:
    """生成"成形参考图"（全分辨率，等比适配 16:9 画框）。Q8 渲染位图参考层。"""
    return fit_contain(panel, frame_w, frame_h)


def _dashed_rect(draw: ImageDraw.ImageDraw, box, color, width=3, dash=18, gap=12):
    x0, y0, x1, y1 = box
    # 四条边，交替画实线段形成虚线
    def hline(y):
        x = x0
        while x < x1:
            draw.line([(x, y), (min(x + dash, x1), y)], fill=color, width=width)
            x += dash + gap

    def vline(x):
        y = y0
        while y < y1:
            draw.line([(x, y), (x, min(y + dash, y1))], fill=color, width=width)
            y += dash + gap

    hline(y0)
    hline(y1)
    vline(x0)
    vline(x1)


def paste_picture(canvas: Image.Image, panel: Image.Image, box, *, inset: int = 8,
                  mode: str = "contain", white_fill: bool = True,
                  bleed_indicator: bool = False) -> dict:
    """把 panel 贴合入 canvas 的 PICTURE 矩形 box=(x0,y0,x1,y1)。

    mode: contain（整幅可见、少量留白）| cover（充满并居中裁切，用于超框/bleed 表达）。
    返回贴合诊断（实际矩形与是否裁切），便于测试与日志。
    """
    x0, y0, x1, y1 = box
    x0 += inset; y0 += inset; x1 -= inset; y1 -= inset
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return {"ok": False}
    if white_fill:
        canvas.paste(Image.new("RGB", (w, h), WHITE), (x0, y0))
    if mode == "cover":
        pic = fit_cover(panel, w, h)
        cropped = True
    else:
        pic = fit_contain(panel, w, h)
        cropped = False
    canvas.paste(pic, (x0, y0))
    if bleed_indicator:
        d = ImageDraw.Draw(canvas)
        _dashed_rect(d, (x0 + 2, y0 + 2, x1 - 2, y1 - 2), _BLEED_COLOR, width=3)
    return {"ok": True, "rect": (x0, y0, x1, y1), "mode": mode, "cropped": cropped,
            "bleed": bool(bleed_indicator)}
