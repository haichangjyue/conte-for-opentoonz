# SPDX-License-Identifier: BSD-3-Clause
"""A4·5-cut 版式坐标（**向后兼容 shim**）。

P4 起，版式坐标的权威来源是 `konte-format/templates/*.json`（见 `konte_poc.template`）。
本模块保留旧的模块级常量与 `rows()/paginate()` API，供既有脚本/测试继续使用，
数值均从默认模板 `scfilms_storyboard.json` 推导，与《模板解析_scfilms_StoryBoard.md》一致。
新代码请直接用 `konte_poc.template.Template`。
"""

from __future__ import annotations

from .template import Column, Row, default_template, paginate as _paginate

_TPL = default_template()

CANVAS_W = _TPL.canvas_w
CANVAS_H = _TPL.canvas_h
DPI = _TPL.dpi

# ---- 列 x 边界 ----
CUT_X0, CUT_X1 = _TPL.columns["cut"].x0, _TPL.columns["cut"].x1
PIC_X0, PIC_X1 = _TPL.columns["picture"].x0, _TPL.columns["picture"].x1
ACTION_X0, ACTION_X1 = _TPL.columns["action"].x0, _TPL.columns["action"].x1
DIALOG_X0, DIALOG_X1 = _TPL.columns["dialogue"].x0, _TPL.columns["dialogue"].x1
MUSIC_X0, MUSIC_X1 = _TPL.columns["music"].x0, _TPL.columns["music"].x1
DUR_X0, DUR_X1 = _TPL.columns["duration"].x0, _TPL.columns["duration"].x1
TEXT_X0, TEXT_X1 = ACTION_X0, MUSIC_X1

# ---- 行 y 边界 ----
HEADER_Y0, HEADER_Y1 = _TPL.header.y0, _TPL.header.y1
ROW_TOPS = [r.y0 for r in _TPL.rows]
ROW_BOTTOMS = [r.y1 for r in _TPL.rows]
ROWS = list(zip(ROW_TOPS, ROW_BOTTOMS))

# ---- 装饰区 ----
_deco = _TPL.decorations
NO_LINE = (_deco["noLabel"]["x"], _deco["noLabel"]["y"],
           _deco["noLine"]["x1"], _deco["noLine"]["y1"])
_b = _deco["pageTotalBox"]
PAGE_TOTAL_BOX = (_b["x0"], _b["y0"], _b["x1"], _b["y1"])

PER_PAGE = _TPL.per_page

__all__ = [
    "CANVAS_W", "CANVAS_H", "DPI",
    "CUT_X0", "CUT_X1", "PIC_X0", "PIC_X1", "TEXT_X0", "TEXT_X1",
    "DUR_X0", "DUR_X1", "ACTION_X0", "ACTION_X1", "DIALOG_X0", "DIALOG_X1",
    "MUSIC_X0", "MUSIC_X1", "HEADER_Y0", "HEADER_Y1",
    "ROW_TOPS", "ROW_BOTTOMS", "ROWS", "NO_LINE", "PAGE_TOTAL_BOX", "PER_PAGE",
    "Row", "Column", "rows", "paginate", "default_template",
]


def rows() -> list[Row]:
    return _TPL.rows


def paginate(cuts: list, per_page: int = PER_PAGE) -> list[list]:
    return _paginate(cuts, per_page)
