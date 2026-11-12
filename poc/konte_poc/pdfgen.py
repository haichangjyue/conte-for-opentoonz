# SPDX-License-Identifier: BSD-3-Clause
"""A4 分镜 PDF 生成（叠图法，Q4）—— P4 模板驱动版。

版式坐标、字体、内边距、超框/bleed 策略全部来自模板（`konte_poc.template`），
默认模板 = `konte-format/templates/scfilms_storyboard.json`（A4 5-cut 基准）。
换模板 = 换一个模板 JSON（或换底版 PSD），`pdfgen` 不再硬编码任何坐标。
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

try:
    from PIL import ImageDraw
except Exception:  # pragma: no cover
    ImageDraw = None

from . import render, textfit
from .model import KonteProject
from .template import Template, coerce_template


def _cut_label(cut: dict) -> str:
    """CUT 列显示用的镜头号：纯数字（1 起），不用 C001 形式。"""
    n = cut.get("number")
    if isinstance(n, (int, float)) and int(n) > 0:
        return str(int(n))
    m = re.search(r"(\d+)", str(cut.get("cut", "")) or "")
    return str(int(m.group(1))) if m else str(cut.get("cut", ""))


# ---------------------------------------------------------------- 底版
def _load_base(base_psd: str | Path | None, tpl: Template) -> Image.Image:
    """加载空白底版：显式 PSD > 模板 basePsd > 内置矢量网格。

    传 base_psd="" 可强制使用内置网格（测试/无底版环境）。
    """
    candidate = base_psd if base_psd != "" else None
    if candidate is None and base_psd != "":
        candidate = tpl.base_psd
    if candidate:
        p = Path(candidate)
        if p.exists():
            with Image.open(p) as _im:
                im = _im.convert("RGB")
            if im.size != tpl.canvas:
                im = im.resize(tpl.canvas, Image.LANCZOS)
            return im
    return _blank_base(tpl)


def _blank_base(tpl: Template) -> Image.Image:
    """无 PSD 时的兜底：按模板坐标画出版式网格（近似模板）。"""
    im = Image.new("RGB", tpl.canvas, (255, 255, 255))
    d = ImageDraw.Draw(im)
    black = (30, 30, 30)
    fr = tpl.data.get("frame", {})
    rows = tpl.rows
    header = tpl.header
    inner = fr.get("inner", {})
    ix0 = int(inner.get("x0", min(c.x0 for c in tpl.columns.values())))
    ix1 = int(inner.get("x1", max(c.x1 for c in tpl.columns.values())))
    iy0 = int(inner.get("y0", header.y0))
    iy1 = int(inner.get("y1", rows[-1].y1))

    outer = fr.get("outer")
    if outer:
        d.rectangle([outer["x0"], outer["y0"], outer["x1"], outer["y1"]],
                    outline=black, width=int(outer.get("borderWidth", 3)))
    vw = int(fr.get("verticalLineWidth", 2))
    for x in tpl.vertical_boundaries():
        d.line([x, iy0, x, iy1], fill=black, width=vw)
    heavy = set(int(y) for y in fr.get("heavyYs", [header.y0, rows[-1].y1]))
    hw = int(fr.get("horizontalLineWidth", 1))
    hwd = int(fr.get("heavyLineWidth", 3))
    for y in [header.y0] + [r.y1 for r in rows]:
        d.line([ix0, y, ix1, y], fill=black, width=(hwd if y in heavy else hw))

    # 表头文字
    for lab in tpl.decorations.get("headerLabels", []):
        spec = tpl.font(lab.get("font", "header"))
        d.text((lab["x"], lab["y"]), lab.get("text", ""),
               font=textfit.get_font(spec.size, spec.bold, spec.family), fill=black)

    # No.
    deco = tpl.decorations
    nl = deco.get("noLabel", {})
    if nl:
        spec = tpl.font(nl.get("font", "decor"))
        size = int(nl.get("size", spec.size))
        d.text((nl["x"], nl["y"]), nl.get("text", "No."),
               font=textfit.get_font(size, spec.bold, spec.family), fill=black)
    ln = deco.get("noLine", {})
    if ln:
        d.line([ln["x0"], ln["y0"], ln["x1"], ln["y1"]], fill=black, width=int(ln.get("width", 2)))
    # 右下 ( + )
    hint = deco.get("pageTotalHint", {})
    if hint:
        spec = tpl.font(hint.get("font", "decor"))
        size = int(hint.get("size", spec.size))
        d.text((hint["x"], hint["y"]), hint.get("text", ""),
               font=textfit.get_font(size, spec.bold, spec.family), fill=black)
    return im


# ---------------------------------------------------------------- 文本
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


def _dialogue_line_text(line) -> str:
    if isinstance(line, str):
        return line
    ch = line.get("character")
    txt = line.get("text", "")
    s = f"{ch}：{txt}" if ch else txt
    if line.get("offscreen"):
        s += "（Off）"
    return s


def _dialogue_text(cut: dict) -> str:
    return "\n".join(_dialogue_line_text(line) for line in cut.get("dialogue", []))


def _music_line_text(m) -> str:
    if isinstance(m, str):
        return m
    txt = m.get("text", "")
    at = m.get("atFrame")
    return f"{txt}［{at}f］" if at is not None else txt


def _music_text(cut: dict) -> str:
    return "\n".join(_music_line_text(m) for m in cut.get("musicSe", []))


def _draw_text_spec_fit(draw, text: str, box, spec, tpl: Template, *, align=None, valign=None,
                        max_lines=None):
    return textfit.fit_block(
        draw, text, box,
        size=spec.size, bold=spec.bold, family=spec.family,
        line_spacing=spec.line_spacing,
        pad=int(tpl.text.get("pad", 10)),
        align=align or tpl.text.get("align", "left"),
        valign=valign or tpl.text.get("valign", "top"),
        min_size=spec.min_size,
        overflow=spec.overflow,
        max_lines=spec.max_lines if max_lines is None else max_lines,
        kinsoku=bool(tpl.text.get("kinsoku", False)),
    )


# ---------------------------------------------------------------- 合成
def _panel_or_placeholder(project: KonteProject, cut: dict, drawing: dict) -> Image.Image:
    try:
        return render.load_panel(project.resolve_drawing(cut, drawing))
    except FileNotFoundError:
        fw = int(project.project["frame"]["width"])
        fh = int(project.project["frame"]["height"])
        im = Image.new("RGB", (fw, fh), (205, 205, 205))
        d = ImageDraw.Draw(im)
        d.rectangle([4, 4, fw - 5, fh - 5], outline=(90, 90, 90), width=4)
        f = textfit.get_font(max(20, fh // 12), bold=True)
        try:
            d.text((fw / 2, fh / 2), f"缺画面\n{cut.get('cut', cut['id'])}",
                   font=f, fill=(70, 70, 70), anchor="mm")
        except Exception:
            pass
        return im


def _distribute(items: list, n: int) -> list[list]:
    """把 items 尽量平均分配到 n 个行格：不足 n 个时一行一个，多则按比例分组。"""
    n = max(1, n)
    if len(items) <= n:
        return [[items[i]] if i < len(items) else [] for i in range(n)]
    groups: list[list] = [[] for _ in range(n)]
    for i, it in enumerate(items):
        groups[min(n - 1, i * n // len(items))].append(it)
    return groups


def _iter_layout_pages(project: KonteProject, tpl, base):
    """按 cut.layout（page/rowStart/rowSpan）排版：一个镜头可跨多个格子、每格一张画面。"""
    fps = project.fps
    rows = tpl.rows
    cut_spec = tpl.font("cut")
    action_spec = tpl.font("action")
    dialogue_spec = tpl.font("dialogue")
    music_spec = tpl.font("music")
    dur_spec = tpl.font("duration")
    page_no_spec = tpl.font("pageNo")
    page_total_spec = tpl.font("pageTotal")
    pic_cfg = tpl.picture
    deco = tpl.decorations

    # ---- 统一布局：无 layout 的按顺序摆放；显式 layout 原位优先、冲突自动找空位/新页 ----
    cuts = project.sorted_cuts()

    def _has_layout(c):
        lay = c.get("layout") or {}
        return ("page" in lay) and ("rowStart" in lay) and ("rowSpan" in lay)

    occupied: dict[int, set] = {}
    placements: dict[str, tuple[int, int, int]] = {}

    # 1) 无 layout 的镜头：每页 rows 个，顺序摆放
    apage, arow = 1, 0
    for c in [x for x in cuts if not _has_layout(x)]:
        while True:
            occ = occupied.setdefault(apage, set())
            if arow < len(rows) and arow not in occ:
                break
            arow += 1
            if arow >= len(rows):
                apage += 1
                arow = 0
        occ.add(arow)
        placements[c["id"]] = (apage, arow, 1)
        arow += 1

    def _find_block(page, span):
        occ = occupied.setdefault(page, set())
        for start in range(0, len(rows) - span + 1):
            if all((start + i) not in occ for i in range(span)):
                return start
        return None

    # 2) 显式 layout：原位优先，冲突则本页找空块 → 其他页 → 新页
    for c in [x for x in cuts if _has_layout(x)]:
        lay = c["layout"]
        p = int(lay.get("page", 1))
        rs = max(0, int(lay.get("rowStart", 0)))
        span = max(1, min(int(lay.get("rowSpan", 1)), len(rows)))
        if rs + span <= len(rows) and all((rs + i) not in occupied.get(p, set())
                                          for i in range(span)):
            place = rs
        else:
            place = _find_block(p, span)
            if place is None:
                for q in sorted(occupied):
                    place = _find_block(q, span)
                    if place is not None:
                        p = q
                        break
            if place is None:
                p = (max(occupied) + 1) if occupied else 1
                place = 0
        occupied.setdefault(p, set()).update(range(place, place + span))
        placements[c["id"]] = (p, place, span)

    by_page: dict[int, list] = {}
    for c in cuts:
        p, rs0, span0 = placements[c["id"]]
        by_page.setdefault(p, []).append((rs0, c, span0))

    for pi in sorted(by_page):
        canvas = base.copy()
        draw = ImageDraw.Draw(canvas)
        page_frames = 0
        for rs, cut, span in sorted(by_page[pi], key=lambda t: (t[0], t[1].get("order", 0))):
            band = rows[rs:min(len(rows), rs + span)]
            if not band:
                band = rows[0:1]
            y0, y1 = band[0].y0, band[-1].y1
            drawings = cut["drawings"]
            for k, row in enumerate(band):
                dr = drawings[k] if k < len(drawings) else drawings[0]
                panel = _panel_or_placeholder(project, cut, dr)
                is_over = cut.get("frame", {}).get("kind") == "oversize"
                mode = pic_cfg.get("oversizeMode", pic_cfg.get("mode", "contain")) if is_over \
                    else pic_cfg.get("mode", "contain")
                bleed = bool(pic_cfg.get("bleedIndicator", False)) and is_over
                render.paste_picture(canvas, panel, tpl.picture_box(row),
                                     inset=int(pic_cfg.get("inset", 8)), mode=mode,
                                     white_fill=bool(pic_cfg.get("whiteFill", True)),
                                     bleed_indicator=bleed)
            cbox = tpl.cell_box("cut", band[0])
            textfit.draw_aligned(draw, _cut_label(cut),
                                 (cbox[0] + 4, y0, cbox[2] - 4, y1),
                                 size=cut_spec.size, bold=cut_spec.bold, family=cut_spec.family,
                                 halign="center", valign="top", pad=10)
            # 文本：跨格时按“段落/条目”分布到各格（贴近真实分镜写法），单格则整块绘制
            a_col = tpl.columns["action"]
            d_col = tpl.columns["dialogue"]
            m_col = tpl.columns["music"]
            action_segs = [p for p in str(cut.get("action", "")).split("\n\n") if p.strip()]
            d_lines = [_dialogue_line_text(x) for x in cut.get("dialogue", [])]
            m_items = [_music_line_text(x) for x in cut.get("musicSe", [])]

            if span > 1 and len(action_segs) > 1:
                for k, row in enumerate(band):
                    txt = "\n".join(_distribute(action_segs, span)[k])
                    if txt:
                        _draw_text_spec_fit(draw, txt, (a_col.x0, row.y0, a_col.x1, row.y1),
                                            action_spec, tpl, max_lines=0)
            else:
                _draw_text_spec_fit(draw, cut.get("action", ""), (a_col.x0, y0, a_col.x1, y1),
                                    action_spec, tpl, max_lines=0)

            if span > 1 and len(d_lines) > 1:
                for k, row in enumerate(band):
                    txt = "\n".join(_distribute(d_lines, span)[k])
                    if txt:
                        _draw_text_spec_fit(draw, txt, (d_col.x0, row.y0, d_col.x1, row.y1),
                                            dialogue_spec, tpl, max_lines=0)
            else:
                _draw_text_spec_fit(draw, _dialogue_text(cut), (d_col.x0, y0, d_col.x1, y1),
                                    dialogue_spec, tpl, max_lines=0)

            if span > 1 and len(m_items) > 1:
                for k, row in enumerate(band):
                    txt = "\n".join(_distribute(m_items, span)[k])
                    if txt:
                        _draw_text_spec_fit(draw, txt, (m_col.x0, row.y0, m_col.x1, row.y1),
                                            music_spec, tpl, max_lines=0)
            else:
                _draw_text_spec_fit(draw, _music_text(cut), (m_col.x0, y0, m_col.x1, y1),
                                    music_spec, tpl, max_lines=0)
            dbox = tpl.cell_box("duration", band[0])
            textfit.draw_aligned(draw, _dur_notation(cut, fps), (dbox[0], y0, dbox[2], y1),
                                 size=dur_spec.size, bold=dur_spec.bold, family=dur_spec.family,
                                 halign="center", valign="bottom", pad=10)
            page_frames += project.total_frames(cut)

        nl = deco.get("noLabel", {})
        ln = deco.get("noLine", {})
        pno = deco.get("pageNo", {})
        label_font = textfit.get_font(int(nl.get("size", 40)), False,
                                      tpl.font(nl.get("font", "decor")).family)
        no_w = label_font.getlength(nl.get("text", "No."))
        cx = (nl.get("x", 77) + no_w + 6 + ln.get("x1", 300)) / 2
        pno_size = int(pno.get("size", page_no_spec.size))
        draw.text((cx, ln.get("y0", 296) - 10), str(pi),
                  font=textfit.get_font(pno_size, page_no_spec.bold, page_no_spec.family),
                  fill=(0, 0, 0), anchor="ms")
        sec, frm = divmod(page_frames, fps)
        b = deco.get("pageTotalBox", {"x0": 2247, "y0": 3312, "x1": 2398, "y1": 3352})
        textfit.draw_centered(draw, f"{sec}+{frm:02d}",
                              (b["x0"], b["y0"], b["x1"], b["y1"]),
                              size=page_total_spec.size, bold=page_total_spec.bold,
                              family=page_total_spec.family)
        yield canvas, {"page": pi, "cutIds": [t[1]["id"] for t in by_page[pi]],
                       "pageTotalFrames": page_frames, "pageTotalNotation": f"{sec}+{frm:02d}"}


def iter_pages(
    project: KonteProject,
    base_psd: str | Path | None = None,
    *,
    per_page: int | None = None,
    template: "Template | dict | str | Path | None" = None,
):
    """逐页生成 (canvas, page_info)，不一次性驻留全部页（P5 流式 PDF 用）。"""
    tpl = coerce_template(template)
    fps = project.fps
    cuts = project.sorted_cuts()
    pages = _paginate(cuts, per_page or tpl.per_page)
    base = _load_base(base_psd, tpl)

    cut_spec = tpl.font("cut")
    action_spec = tpl.font("action")
    dialogue_spec = tpl.font("dialogue")
    music_spec = tpl.font("music")
    dur_spec = tpl.font("duration")
    page_no_spec = tpl.font("pageNo")
    page_total_spec = tpl.font("pageTotal")
    pic_cfg = tpl.picture
    rows = tpl.rows
    deco = tpl.decorations

    # 真实分镜：存在 cut.layout 时走“跨格”排版
    if any(c.get("layout") for c in cuts):
        yield from _iter_layout_pages(project, tpl, base)
        return

    for pi, page_cuts in enumerate(pages, start=1):
        canvas = base.copy()
        draw = ImageDraw.Draw(canvas)
        page_frames = 0
        for ri, cut in enumerate(page_cuts):
            if ri >= len(rows):
                break
            row = rows[ri]
            # 1) 画面（超框 cut 用 oversizeMode + bleed 提示）
            panel_path = project.resolve_level(cut)
            panel = render.load_panel(panel_path)
            is_over = cut.get("frame", {}).get("kind") == "oversize"
            mode = pic_cfg.get("oversizeMode", pic_cfg.get("mode", "contain")) if is_over \
                else pic_cfg.get("mode", "contain")
            bleed = bool(pic_cfg.get("bleedIndicator", False)) and is_over
            render.paste_picture(
                canvas, panel, tpl.picture_box(row),
                inset=int(pic_cfg.get("inset", 8)), mode=mode,
                white_fill=bool(pic_cfg.get("whiteFill", True)), bleed_indicator=bleed,
            )
            # 2) CUT 号（贴行顶）
            cbox = tpl.cell_box("cut", row)
            textfit.draw_aligned(draw, _cut_label(cut),
                                 (cbox[0] + 4, row.y0, cbox[2] - 4, row.y1),
                                 size=cut_spec.size, bold=cut_spec.bold, family=cut_spec.family,
                                 halign="center", valign="top", pad=10)
            # 3) ACTION
            _draw_text_spec_fit(draw, cut.get("action", ""), tpl.cell_box("action", row), action_spec, tpl)
            # 4) DIALOGE
            _draw_text_spec_fit(draw, _dialogue_text(cut), tpl.cell_box("dialogue", row), dialogue_spec, tpl)
            # 5) MUSIC/SE
            _draw_text_spec_fit(draw, _music_text(cut), tpl.cell_box("music", row), music_spec, tpl)
            # 6) Dur.（贴行底）
            dbox = tpl.cell_box("duration", row)
            textfit.draw_aligned(draw, _dur_notation(cut, fps), dbox,
                                 size=dur_spec.size, bold=dur_spec.bold, family=dur_spec.family,
                                 halign="center", valign="bottom", pad=10)
            page_frames += project.total_frames(cut)

        # 页 No.：放在“No.”到横线末端的中间，字号更大
        nl = deco.get("noLabel", {})
        ln = deco.get("noLine", {})
        pno = deco.get("pageNo", {})
        label_font = textfit.get_font(int(nl.get("size", 40)), False,
                                      tpl.font(nl.get("font", "decor")).family)
        no_w = label_font.getlength(nl.get("text", "No."))
        x_start = nl.get("x", 77) + no_w + 6
        x_end = ln.get("x1", 300)
        cx = (x_start + x_end) / 2
        baseline_y = ln.get("y0", 296) - 10
        pno_size = int(pno.get("size", page_no_spec.size))
        draw.text((cx, baseline_y), str(pi),
                  font=textfit.get_font(pno_size, page_no_spec.bold, page_no_spec.family),
                  fill=(0, 0, 0), anchor="ms")
        # 页合计 ( + )
        sec, frm = divmod(page_frames, fps)
        b = deco.get("pageTotalBox", {"x0": 2247, "y0": 3312, "x1": 2398, "y1": 3352})
        textfit.draw_centered(draw, f"{sec}+{frm:02d}",
                              (b["x0"], b["y0"], b["x1"], b["y1"]),
                              size=page_total_spec.size, bold=page_total_spec.bold, family=page_total_spec.family)
        info = {
            "page": pi,
            "cutIds": [c["id"] for c in page_cuts],
            "pageTotalFrames": page_frames,
            "pageTotalNotation": f"{sec}+{frm:02d}",
        }
        yield canvas, info


def compose_pages(
    project: KonteProject,
    base_psd: str | Path | None = None,
    *,
    per_page: int | None = None,
    template: "Template | dict | str | Path | None" = None,
) -> tuple[list[Image.Image], list[dict]]:
    """把 cut 合成为每页图像（不落盘），返回 (page_images, page_infos)。"""
    pairs = list(iter_pages(project, base_psd, per_page=per_page, template=template))
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _paginate(cuts: list, per_page: int) -> list[list]:
    from .template import paginate as _pg
    return _pg(cuts, per_page)


STREAM_THRESHOLD_PAGES = 8  # 超过该页数自动改用流式写 PDF（内存 O(1 页)）


def build_storyboard_pdf(
    project: KonteProject,
    out_path: str | Path,
    base_psd: str | Path | None = None,
    *,
    per_page: int | None = None,
    template: "Template | dict | str | Path | None" = None,
    streaming: bool | None = None,
) -> list[dict]:
    """生成分镜 PDF；返回每页信息列表。

    streaming=None 时自动：页数 > STREAM_THRESHOLD_PAGES 用流式（逐页 Flate），否则 Pillow 一次写。
    流式路径任意时刻只驻留 1 页位图，>200 cut（40+ 页）不致内存爆炸。
    """
    from .pdfstream import write_pdf_streaming

    tpl = coerce_template(template)
    per = per_page or tpl.per_page
    total_cuts = len(project.sorted_cuts())
    total_pages = (total_cuts + per - 1) // per if total_cuts else 0
    use_stream = (total_pages > STREAM_THRESHOLD_PAGES) if streaming is None else bool(streaming)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not use_stream:
        page_images, page_infos = compose_pages(project, base_psd, per_page=per, template=tpl)
        if page_images:
            page_images[0].save(
                out_path, "PDF", resolution=tpl.dpi, save_all=True,
                append_images=page_images[1:],
            )
        return page_infos

    page_infos: list[dict] = []

    def _gen():
        for im, info in iter_pages(project, base_psd, per_page=per, template=tpl):
            page_infos.append(info)
            yield im

    write_pdf_streaming(_gen(), out_path, dpi=tpl.dpi)
    return page_infos


def build_storyboard_pdfs_split(
    project: KonteProject,
    out_dir: str | Path,
    base_psd: str | Path | None = None,
    *,
    per_page: int | None = None,
    template: "Template | dict | str | Path | None" = None,
    pages_per_file: int = 10,
    stem: str = "storyboard",
) -> dict:
    """分卷输出：每 pages_per_file 页一个 PDF（逐卷流式写）。返回 {files, pageInfos}。"""
    from .pdfstream import write_pdf_streaming
    import itertools

    tpl = coerce_template(template)
    per = per_page or tpl.per_page
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    it = iter_pages(project, base_psd, per_page=per, template=tpl)
    files: list[str] = []
    infos: list[dict] = []
    part = 1
    pages_per_file = max(1, int(pages_per_file))
    while True:
        chunk = list(itertools.islice(it, pages_per_file))
        if not chunk:
            break
        path = out_dir / f"{stem}.part{part:02d}.pdf"
        write_pdf_streaming((im for im, _ in chunk), path, dpi=tpl.dpi)
        infos.extend(info for _, info in chunk)
        files.append(str(path))
        part += 1
    return {"files": files, "pageInfos": infos}
