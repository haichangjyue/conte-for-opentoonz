# SPDX-License-Identifier: BSD-3-Clause
"""A4·5-cut 版式坐标（源自《模板解析_scfilms_StoryBoard.md》对 scfilms_StoryBoard.psd 的实测）。

画布 2480×3507 @300dpi（A4 竖版）。所有坐标为像素，原点左上。
"""

from __future__ import annotations

from dataclasses import dataclass

CANVAS_W = 2480
CANVAS_H = 3507
DPI = 300

# ---- 列 x 边界 ----
CUT_X0, CUT_X1 = 96, 210
PIC_X0, PIC_X1 = 210, 1245
TEXT_X0, TEXT_X1 = 1266, 2259
DUR_X0, DUR_X1 = 2259, 2376
# 文字大区内部（可微调）
ACTION_X0, ACTION_X1 = 1266, 1600
DIALOG_X0, DIALOG_X1 = 1600, 1950
MUSIC_X0, MUSIC_X1 = 1950, 2259

# ---- 行 y 边界 ----
HEADER_Y0, HEADER_Y1 = 354, 417
ROW_TOPS = [417, 984, 1557, 2130, 2703]
ROW_BOTTOMS = [984, 1557, 2130, 2703, 3276]
ROWS = list(zip(ROW_TOPS, ROW_BOTTOMS))

# ---- 装饰区 ----
NO_LINE = (77, 258, 300, 296)          # No. ____ 区域 (x0,y0,x1,y1)
PAGE_TOTAL_BOX = (2247, 3312, 2398, 3352)  # 右下 ( + )

PER_PAGE = 5


@dataclass(frozen=True)
class Row:
    index: int          # 0..4
    y0: int
    y1: int

    @property
    def height(self) -> int:
        return self.y1 - self.y0


def rows() -> list[Row]:
    return [Row(i, y0, y1) for i, (y0, y1) in enumerate(ROWS)]


def paginate(cuts: list, per_page: int = PER_PAGE) -> list[list]:
    """按顺序每页切 per_page 个 cut。"""
    return [cuts[i:i + per_page] for i in range(0, len(cuts), per_page)]
