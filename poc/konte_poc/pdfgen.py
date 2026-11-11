# SPDX-License-Identifier: BSD-3-Clause
"""A4·5-cut 分镜 PDF 生成（叠图法，Q4）。

以 scfilms_StoryBoard.psd 合成为空白底版，按实测坐标叠加每个 cut 的画面与文字。
每页 5 个 cut，超出自动分页。输出为 A4（含 300dpi 元数据）PDF。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

try:
    from PIL import ImageDraw
except Exception:  # pragma: no cover
    ImageDraw = None

from . import layout, render, textfit
from .model import KonteProject


def _load_base(base_psd: str | Path | None) -> Image.Image:
    if base_psd:
        p = Path(base_psd)
        if p.exists():
            im = Image.open(p).convert("RGB")
            if im.size != (layout.CANVAS_W, layout.CANVAS_H):
                im = im.resize((layout.CANVAS_W, layout.CANVAS_H), Image.LANCZOS)
            return im
    return _blank_base()


def _blank_base() -> Image.Image:
    """无 PSD 时的兜底：按实测坐标画出版式网格（近似模板）。"""
    im = Image.new("RGB", (layout.CANVAS_W, layout.CANVAS_H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    black = (30, 30, 30)
    # 外框
    d.rectangle([75, 336, 2394, 3294], outline=black, width=3)
    # 竖线
    for x in (96, 210, 1245, 1266, 1600, 1950, 2259, 2376):
        d.line([x, 354, x, 3276], fill=black, width=2)
    # 横线
    for y in [354] + layout.ROW_BOTTOMS:
        d.line([96, y, 2376, y], fill=black, width=3 if y in (417, 3276) else 1)
    d.line([96, 354, 2376, 354], fill=black, width=3)
    # 表头文字
    f = textfit.get_font(28)
    for label, x in [("CUT", 120), ("PICTURE", 660), ("ACTION", 1300),
                     ("DIALOGE", 1680), ("MUSIC/SE", 2000), ("Dur.", 2295)]:
        d.text((x, 366), label, font=f, fill=black)
    # No.
    d.text((77, 258), "No.", font=textfit.get_font(40), fill=black)
    d.line([150, 296, 300, 296], fill=black, width=2)
    # 右下 ( + )
    d.text((2270, 3312), "(    +    )", font=textfit.get_font(30), fill=black)
    return im


def _dur_notation(cut: dict, fps: int) -> str:
    dur = cut["duration"]
    if dur["status"] == "tbd":
        return "TBD"
    sec = dur.get("seconds")
    frm = dur.get("frames")
    if sec is None or frm is None:
        total = int(dur["totalFrames"])
        sec, frm = divmod(total, fps)
    return f"{sec}+{frm:02d}"


def _dialogue_text(cut: dict) -> str:
    out = []
    for line in cut.get("dialogue", []):
        if isinstance(line, str):
            out.append(line)
            continue
        ch = line.get("character")
        txt = line.get("text", "")
        s = f"{ch}：{txt}" if ch else txt
        if line.get("offscreen"):
            s += "（Off）"
        out.append(s)
    return "\n".join(out)


def _music_text(cut: dict) -> str:
    out = []
    for m in cut.get("musicSe", []):
        if isinstance(m, str):
            out.append(m)
            continue
        txt = m.get("text", "")
        at = m.get("atFrame")
        out.append(f"{txt}［{at}f］" if at is not None else txt)
    return "\n".join(out)


def compose_pages(
    project: KonteProject,
    base_psd: str | Path | None = None,
    *,
    per_page: int = layout.PER_PAGE,
) -> tuple[list[Image.Image], list[dict]]:
    """把 cut 合成为每页图像（不落盘），返回 (page_images, page_infos)。"""
    fps = project.fps
    cuts = project.sorted_cuts()
    pages = layout.paginate(cuts, per_page)
    base = _load_base(base_psd)
    page_images: list[Image.Image] = []
    page_infos: list[dict] = []

    for pi, page_cuts in enumerate(pages, start=1):
        canvas = base.copy()
        draw = ImageDraw.Draw(canvas)
        page_frames = 0
        for ri, cut in enumerate(page_cuts):
            row = layout.rows()[ri]
            # 1) 画面
            panel_path = project.resolve_level(cut)
            panel = render.load_panel(panel_path)
            render.paste_picture(canvas, panel,
                                 (layout.PIC_X0, row.y0, layout.PIC_X1, row.y1))
            # 2) CUT 号
            textfit.draw_centered(draw, cut.get("cut", ""),
                                  (layout.CUT_X0 + 4, row.y0, layout.CUT_X1 - 4, row.y1),
                                  size=40, bold=True)
            # 3) ACTION
            textfit.fit_block(draw, cut.get("action", ""),
                              (layout.ACTION_X0, row.y0, layout.ACTION_X1, row.y1),
                              size=30, line_spacing=1.18)
            # 4) DIALOGE
            textfit.fit_block(draw, _dialogue_text(cut),
                              (layout.DIALOG_X0, row.y0, layout.DIALOG_X1, row.y1),
                              size=30, line_spacing=1.18)
            # 5) MUSIC/SE
            textfit.fit_block(draw, _music_text(cut),
                              (layout.MUSIC_X0, row.y0, layout.MUSIC_X1, row.y1),
                              size=28, line_spacing=1.18)
            # 6) Dur.
            textfit.draw_centered(draw, _dur_notation(cut, fps),
                                  (layout.DUR_X0, row.y0, layout.DUR_X1, row.y1),
                                  size=40)
            page_frames += project.total_frames(cut)

        # 页 No.
        draw.text((160, 258), str(pi), font=textfit.get_font(44), fill=(0, 0, 0))
        # 页合计 ( + )
        sec, frm = divmod(page_frames, fps)
        bx = layout.PAGE_TOTAL_BOX
        textfit.draw_centered(draw, f"{sec}+{frm:02d}", (bx[0], bx[1], bx[2], bx[3]),
                              size=34)
        page_images.append(canvas)
        page_infos.append({
            "page": pi,
            "cutIds": [c["id"] for c in page_cuts],
            "pageTotalFrames": page_frames,
            "pageTotalNotation": f"{sec}+{frm:02d}",
        })

    return page_images, page_infos


def build_storyboard_pdf(
    project: KonteProject,
    out_path: str | Path,
    base_psd: str | Path | None = None,
    *,
    per_page: int = layout.PER_PAGE,
) -> list[dict]:
    """生成 A4·5-cut 分镜 PDF；返回每页信息列表。"""
    page_images, page_infos = compose_pages(project, base_psd, per_page=per_page)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page_images[0].save(
        out_path, "PDF", resolution=layout.DPI, save_all=True,
        append_images=page_images[1:],
    )
    return page_infos
