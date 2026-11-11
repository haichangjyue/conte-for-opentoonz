# SPDX-License-Identifier: BSD-3-Clause
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from konte_poc import layout  # noqa: E402


class TestLayout(unittest.TestCase):
    def test_rows(self):
        rows = layout.rows()
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0].y0, 417)
        self.assertEqual(rows[4].y1, 3276)

    def test_paginate(self):
        items = list(range(7))
        pages = layout.paginate(items, 5)
        self.assertEqual([len(p) for p in pages], [5, 2])
        self.assertEqual(pages[1], [5, 6])

    def test_canvas_a4_ratio(self):
        # A4 竖版比例 ~ 1:1.414
        ratio = layout.CANVAS_H / layout.CANVAS_W
        self.assertAlmostEqual(ratio, 1.414, places=2)


if __name__ == "__main__":
    unittest.main()
