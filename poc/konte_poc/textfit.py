# SPDX-License-Identifier: BSD-3-Clause
"""CJK 字体加载 + 文本换行/禁则/溢出绘制工具（P4 增强）。

字体策略（可商用优先，见 LICENSES.md）：
  1. 环境变量 KONTE_FONT（指向单个字体文件）——最高优先级，便于测试/临时替换；
  2. 模板 `fonts.*.family` 指定的字体族；仓库内 `konte-format/fonts/` 优先，其后系统字体；
  3. 回退次序：Noto Sans JP → Noto Sans SC → Microsoft YaHei → MS Gothic → SimSun；
  4. 全缺时退回 PIL 内置默认（仅西文，仅供兜底）。

许可证：默认字体族为 **Noto Sans JP / Noto Sans SC**（SIL OFL 1.1，可商用）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
_FONT_DIRS = [
    Path(os.environ["KONTE_FONT_DIR"]) if os.environ.get("KONTE_FONT_DIR") else None,
    _REPO_ROOT / "konte-format" / "fonts",
    _WIN_FONTS,
]
_FONT_DIRS = [d for d in _FONT_DIRS if d is not None]

# 字体族 → 常规/加粗候选（文件名, ttc 索引）。文件名在 _FONT_DIRS 中查找。
_FAMILIES: dict[str, dict[str, list[tuple[str, int]]]] = {
    "Noto Sans JP": {
        "regular": [("NotoSansJP-VF.ttf", 0), ("NotoSansJP-Regular.otf", 0)],
        "bold": [("NotoSansJP-Bold.otf", 0), ("NotoSansJP-VF.ttf", 0)],
    },
    "Noto Sans SC": {
        "regular": [("NotoSansSC-VF.ttf", 0), ("NotoSansSC-Regular.otf", 0)],
        "bold": [("NotoSansSC-Bold.otf", 0), ("NotoSansSC-VF.ttf", 0)],
    },
    "Source Han Sans": {
        "regular": [("SourceHanSans.ttc", 27)],   # SC Regular
        "bold": [("SourceHanSans.ttc", 37)],      # SC Bold
    },
    "Source Han Sans SC": {
        "regular": [("SourceHanSans.ttc", 27)],
        "bold": [("SourceHanSans.ttc", 37)],
    },
    "Source Han Sans JP": {
        "regular": [("SourceHanSans.ttc", 25)],   # JP Regular
        "bold": [("SourceHanSans.ttc", 35)],      # JP Bold
    },
    "Microsoft YaHei": {
        "regular": [("msyh.ttc", 0)],
        "bold": [("msyhbd.ttc", 0), ("msyh.ttc", 0)],
    },
    "MS Gothic": {
        "regular": [("msgothic.ttc", 0)],
        "bold": [("msgothic.ttc", 0)],
    },
    "SimSun": {
        "regular": [("simsun.ttc", 0)],
        "bold": [("simsun.ttc", 0)],
    },
}
_DEFAULT_FAMILY = "Source Han Sans"
_FALLBACK_ORDER = ["Source Han Sans", "Noto Sans SC", "Noto Sans JP", "Microsoft YaHei", "MS Gothic", "SimSun"]

# 简繁别名归一（大小写/空格不敏感）
_ALIASES = {
    "noto sans jp": "Noto Sans JP",
    "noto sans japanese": "Noto Sans JP",
    "noto sans sc": "Noto Sans SC",
    "noto sans cjk": "Noto Sans SC",
    "noto sans cjk sc": "Noto Sans SC",
    "source han sans": "Source Han Sans",
    "source han sans sc": "Source Han Sans SC",
    "source han sans jp": "Source Han Sans JP",
    "思源黑体": "Source Han Sans",
    "微软雅黑": "Microsoft YaHei",
    "microsoft yahei": "Microsoft YaHei",
    "ms gothic": "MS Gothic",
    "msgothic": "MS Gothic",
    "simsun": "SimSun",
    "宋体": "SimSun",
}


def _norm_family(family: str | None) -> str:
    if not family:
        return _DEFAULT_FAMILY
    key = family.strip()
    return _ALIASES.get(key.lower(), key)


def _candidate_files(family: str, bold: bool) -> list[tuple[str, int]]:
    fam = _norm_family(family)
    res: list[tuple[str, int]] = []
    seen = set()

    def add(f: str):
        d = _FAMILIES.get(f)
        if not d:
            return
        order = ["bold", "regular"] if bold else ["regular", "bold"]
        for key in order:
            for item in d[key]:
                if item not in seen:
                    seen.add(item)
                    res.append(item)

    add(fam)
    for f in _FALLBACK_ORDER:
        add(f)
    return res


@lru_cache(maxsize=1)
def _dir_index() -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for d in _FONT_DIRS:
        try:
            if not d.exists():
                continue
            for p in d.iterdir():
                idx.setdefault(p.name.lower(), p)
        except OSError:
            continue
    return idx


def _find_font_file(family: str | None, bold: bool = False) -> tuple[str, int] | None:
    env = os.environ.get("KONTE_FONT")
    if env and Path(env).exists():
        return (env, 0)

    # 模板 family 直接给了一个字体文件路径
    if family:
        p = Path(family)
        if p.exists() and p.is_file():
            return (str(p), 0)

    idx = _dir_index()
    for name, sub in _candidate_files(_norm_family(family), bold):
        hit = idx.get(name.lower())
        if hit is not None:
            return (str(hit), sub)
    return None


@lru_cache(maxsize=512)
def get_font(size: int, bold: bool = False,
             family: str | None = None) -> ImageFont.FreeTypeFont:
    size = max(1, int(size))
    found = _find_font_file(family, bold)
    if found:
        path, idx = found
        try:
            f = ImageFont.truetype(path, size=size, index=idx)
            if "vf" in Path(path).name.lower() or "variable" in Path(path).name.lower():
                # 可变字体默认实例可能偏细；显式给常用权重（Regular=400 / Bold=700）
                try:
                    f.set_variation_by_axes([700 if bold else 400])
                except Exception:
                    pass
            elif bold:
                try:
                    f.set_variation_by_axes([700])
                except Exception:
                    pass
            return f
        except Exception:
            pass
    return ImageFont.load_default()


def resolved_family(family: str | None = None) -> str | None:
    """返回实际命中的字体文件名（诊断用）。"""
    found = _find_font_file(family, False)
    return Path(found[0]).name if found else None


def _text_width(font: ImageFont.FreeTypeFont, s: str) -> float:
    try:
        return font.getlength(s)
    except Exception:
        bbox = font.getbbox(s)
        return bbox[2] - bbox[0]


# ---- 禁则（日文/中文换行规则，简化版）----
_NO_LINE_START = set("。、，．！？：；）］｝」』】〉》〕…‥ー～・,.:;!?)]}>％%℃")
_NO_LINE_END = set("（［｛「『【〈《〔([{<“‘＄$")


def _tokenize(raw: str) -> list[str]:
    """ASCII 连续字母数字（含部分符号）并为一个词；其余逐字符。"""
    units: list[str] = []
    token = ""
    for ch in raw:
        if ch.isascii() and (ch.isalnum() or ch in "-_/.'"):
            token += ch
        else:
            if token:
                units.append(token)
                token = ""
            units.append(ch)
    if token:
        units.append(token)
    return units


def _hard_split(font: ImageFont.FreeTypeFont, unit: str, max_width: int) -> list[str]:
    parts: list[str] = []
    cur = ""
    for ch in unit:
        if cur and _text_width(font, cur + ch) > max_width:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts or [unit]


def _wrap_one(raw: str, font: ImageFont.FreeTypeFont, max_width: int,
              kinsoku: bool) -> list[str]:
    units = _tokenize(raw)
    lines: list[str] = []
    cur = ""
    for u in units:
        if cur == "":
            if _text_width(font, u) > max_width and len(u) > 1:
                parts = _hard_split(font, u, max_width)
                lines.extend(parts[:-1])
                cur = parts[-1]
            else:
                cur = u
            continue
        if _text_width(font, cur + u) <= max_width:
            cur += u
            continue
        # 需要在此断行
        if kinsoku and u and u[0] in _NO_LINE_START:
            # 行首禁则：把标点留在当前行（允许轻微溢出）
            cur += u
            lines.append(cur)
            cur = ""
            continue
        if kinsoku and cur and cur[-1] in _NO_LINE_END:
            # 行尾禁则：把开括号挪到下一行
            moved = cur[-1]
            cur = cur[:-1]
            if cur:
                lines.append(cur)
            cur = moved + u
            continue
        lines.append(cur)
        if _text_width(font, u) > max_width and len(u) > 1:
            parts = _hard_split(font, u, max_width)
            lines.extend(parts[:-1])
            cur = parts[-1]
        else:
            cur = u
    if cur != "" or not lines:
        lines.append(cur)
    return lines


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int,
         kinsoku: bool = False) -> list[str]:
    """按可用宽度换行；支持 \\n 与中英混排；kinsoku=日文禁则。"""
    lines: list[str] = []
    for raw in str(text).split("\n"):
        if raw == "":
            lines.append("")
            continue
        lines.extend(_wrap_one(raw, font, max_width, kinsoku))
    return lines


def _apply_overflow(lines: list[str], font: ImageFont.FreeTypeFont, max_w: int,
                    max_h: int, line_h: int, overflow: str, max_lines: int,
                    ellipsis: str = "…") -> tuple[list[str], bool]:
    """裁切/省略策略。返回 (lines, truncated)。"""
    truncated = False
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    max_fit = max(1, max_h // max(1, line_h))
    if len(lines) > max_fit:
        lines = lines[:max_fit]
        truncated = True
    if truncated and overflow == "ellipsis" and lines:
        last = lines[-1]
        while last and _text_width(font, last + ellipsis) > max_w:
            last = last[:-1]
        lines[-1] = (last + ellipsis) if last else ellipsis
    return lines, truncated


def fit_block(
    draw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    size: int,
    bold: bool = False,
    family: str | None = None,
    fill=(0, 0, 0),
    line_spacing: float = 1.15,
    pad: int = 10,
    align: str = "left",
    valign: str = "top",
    shrink: bool = True,
    min_size: int = 14,
    overflow: str = "shrink",
    max_lines: int = 0,
    kinsoku: bool = False,
) -> int:
    """在 box 内绘制文本块：自动缩字号（shrink）+ 溢出策略。

    overflow: shrink | truncate | ellipsis | clip
    返回实际使用的字号。
    """
    x0, y0, x1, y1 = box
    max_w = max(1, (x1 - x0) - 2 * pad)
    max_h = max(1, (y1 - y0) - 2 * pad)

    use_size = int(size)
    while True:
        font = get_font(use_size, bold, family)
        lines = wrap(text, font, max_w, kinsoku=kinsoku)
        line_h = max(1, int(round(use_size * line_spacing)))
        total_h = line_h * len(lines)
        if not shrink or total_h <= max_h or use_size <= min_size:
            break
        use_size = max(min_size, use_size - 2)

    font = get_font(use_size, bold, family)
    lines = wrap(text, font, max_w, kinsoku=kinsoku)
    line_h = max(1, int(round(use_size * line_spacing)))
    lines, _ = _apply_overflow(lines, font, max_w, max_h, line_h, overflow, max_lines)

    block_h = line_h * len(lines)
    if valign == "middle":
        ty = y0 + pad + max(0, (max_h - block_h) // 2)
    elif valign == "bottom":
        ty = y1 - pad - block_h
    else:
        ty = y0 + pad
    ty = max(y0 + pad, ty)

    for ln in lines:
        if align == "center":
            draw.text(((x0 + x1) / 2, ty), ln, font=font, fill=fill, anchor="ma")
        elif align == "right":
            draw.text((x1 - pad, ty), ln, font=font, fill=fill, anchor="ra")
        else:
            draw.text((x0 + pad, ty), ln, font=font, fill=fill, anchor="la")
        ty += line_h
    return use_size


def draw_centered(draw, text, box, *, size, bold=False, family: str | None = None,
                  fill=(0, 0, 0)):
    x0, y0, x1, y1 = box
    font = get_font(size, bold, family)
    try:
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), str(text), font=font,
                  fill=fill, anchor="mm")
    except Exception:
        draw.text((x0 + 6, y0 + 6), str(text), font=font, fill=fill)


def draw_aligned(draw, text, box, *, size, bold=False, family: str | None = None,
                 fill=(0, 0, 0), halign: str = "center", valign: str = "top",
                 pad: int = 8):
    """在 box 内按 halign(left/center/right) + valign(top/middle/bottom) 对齐绘制单行文本。

    用于 CUT 号贴行顶、Dur. 贴行底、页码等对位。
    """
    x0, y0, x1, y1 = box
    font = get_font(size, bold, family)
    if halign == "center":
        x, ha = (x0 + x1) / 2, "m"
    elif halign == "right":
        x, ha = x1 - pad, "r"
    else:
        x, ha = x0 + pad, "l"
    if valign == "bottom":
        y, va = y1 - pad, "d"
    elif valign == "middle":
        y, va = (y0 + y1) / 2, "m"
    else:
        y, va = y0 + pad, "a"
    try:
        draw.text((x, y), str(text), font=font, fill=fill, anchor=ha + va)
    except Exception:
        draw.text((x0 + pad, y0 + pad), str(text), font=font, fill=fill)

