# SPDX-License-Identifier: BSD-3-Clause
"""CJK 字体加载与文本换行/绘制工具。

字体优先级（Windows 常见可商用/系统字体），可用环境变量 KONTE_FONT 覆盖：
  1. 环境变量 KONTE_FONT
  2. Microsoft YaHei (msyh.ttc) —— 覆盖中日文
  3. Noto Sans SC / JP VF
  4. MS Gothic / SimSun
若都缺失，退回 PIL 内置默认（仅西文）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

_CANDIDATES = [
    ("msyh.ttc", 0),
    ("msyhbd.ttc", 0),
    ("NotoSansSC-VF.ttf", 0),
    ("NotoSansJP-VF.ttf", 0),
    ("msgothic.ttc", 0),
    ("simsun.ttc", 0),
]


def _find_font_file(bold: bool = False) -> tuple[str, int] | None:
    env = os.environ.get("KONTE_FONT")
    if env and Path(env).exists():
        return (env, 0)
    if bold:
        bold_first = ["msyhbd.ttc", "NotoSansSC-VF.ttf", "NotoSansJP-VF.ttf", "msgothic.ttc"]
        for name in bold_first:
            p = _WIN_FONTS / name
            if p.exists():
                return (str(p), 0)
    for name, idx in _CANDIDATES:
        p = _WIN_FONTS / name
        if p.exists():
            return (str(p), idx)
    return None


@lru_cache(maxsize=64)
def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    found = _find_font_file(bold)
    if found:
        path, idx = found
        try:
            f = ImageFont.truetype(path, size=size, index=idx)
            if bold:
                try:
                    f.set_variation_by_axes([700])  # 可变字体尽量加粗
                except Exception:
                    pass
            return f
        except Exception:
            pass
    return ImageFont.load_default()


def _text_width(font: ImageFont.FreeTypeFont, s: str) -> float:
    try:
        return font.getlength(s)
    except Exception:
        bbox = font.getbbox(s)
        return bbox[2] - bbox[0]


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按可用宽度换行；支持 \n 与中英混排（无空格时按字符断行）。"""
    lines: list[str] = []
    for raw in str(text).split("\n"):
        if raw == "":
            lines.append("")
            continue
        cur = ""
        # 以"词/字符"为单位：ASCII 连续字母数字算一个词，其余逐字符
        token = ""
        def flush_token():
            nonlocal cur, token
            if not token:
                return
            if _text_width(font, cur + token) <= max_width or cur == "":
                cur += token
            else:
                lines.append(cur)
                cur = token
            token = ""
        for ch in raw:
            if ch.isascii() and (ch.isalnum() or ch in "-_/.'"):
                token += ch
            else:
                flush_token()
                if _text_width(font, cur + ch) <= max_width or cur == "":
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
        flush_token()
        lines.append(cur)
    return lines


def fit_block(
    draw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    size: int,
    bold: bool = False,
    fill=(0, 0, 0),
    line_spacing: float = 1.15,
    pad: int = 10,
    align: str = "left",
    valign: str = "top",
    shrink: bool = True,
    min_size: int = 14,
) -> int:
    """在 box 内绘制文本块，超界时自动缩字号（shrink）。

    返回实际使用的字号。逐行绘制；超出盒高则停止（最后一行加省略号是可选项，这里直接裁）。
    """
    x0, y0, x1, y1 = box
    max_w = max(1, (x1 - x0) - 2 * pad)
    max_h = max(1, (y1 - y0) - 2 * pad)

    use_size = size
    while True:
        font = get_font(use_size, bold)
        lines = wrap(text, font, max_w)
        line_h = int(round(use_size * line_spacing))
        total_h = line_h * len(lines)
        if not shrink or total_h <= max_h or use_size <= min_size:
            break
        use_size -= 2

    font = get_font(use_size, bold)
    lines = wrap(text, font, max_w)
    line_h = int(round(use_size * line_spacing))
    if valign == "middle":
        ty = y0 + pad + max(0, (max_h - line_h * len(lines)) // 2)
    elif valign == "bottom":
        ty = y1 - pad - line_h * len(lines)
    else:
        ty = y0 + pad
    ty = max(y0 + pad, ty)

    for ln in lines:
        if ty + line_h > y1 - pad + 2 and ty != y0 + pad:
            break
        draw.text((x0 + pad, ty), ln, font=font, fill=fill, anchor="la")
        ty += line_h
    return use_size


def draw_centered(draw, text, box, *, size, bold=False, fill=(0, 0, 0)):
    x0, y0, x1, y1 = box
    font = get_font(size, bold)
    try:
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), str(text), font=font,
                  fill=fill, anchor="mm")
    except Exception:
        draw.text((x0 + 6, y0 + 6), str(text), font=font, fill=fill)
