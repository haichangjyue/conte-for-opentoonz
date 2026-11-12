# SPDX-License-Identifier: BSD-3-Clause
"""分镜 PDF 版式模板（P4）：坐标外部化 + 校验 + 数据类。

设计目标（见《工程交接技术规格》/ progress.md §4.1）：
  * 把《模板解析_scfilms_StoryBoard.md》实测坐标做成可替换的 JSON 模板；
  * “换一套底版 PSD / 社内模板” = 换一个模板 JSON，`pdfgen.py` 不再硬编码坐标；
  * 模板本身用 `konte-format/pdf-template.schema.json` 做零依赖校验。

坐标一律为像素，原点左上；画布默认 A4 竖版 2480×3507 @300dpi。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import minischema

_REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = _REPO_ROOT / "konte-format" / "templates"
SCHEMA_PATH = _REPO_ROOT / "konte-format" / "pdf-template.schema.json"
DEFAULT_TEMPLATE_PATH = TEMPLATE_DIR / "scfilms_storyboard.json"


class TemplateError(ValueError):
    """模板配置非法（schema 或语义约束失败）。"""


# ---------------------------------------------------------------- 数据类
@dataclass(frozen=True)
class Column:
    x0: int
    x1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    def as_box(self, y0: int, y1: int) -> tuple[int, int, int, int]:
        return (self.x0, y0, self.x1, y1)


@dataclass(frozen=True)
class Band:
    y0: int
    y1: int

    @property
    def height(self) -> int:
        return self.y1 - self.y0


@dataclass(frozen=True)
class Row:
    index: int
    y0: int
    y1: int

    @property
    def height(self) -> int:
        return self.y1 - self.y0


@dataclass(frozen=True)
class FontSpec:
    family: str
    size: int
    bold: bool = False
    line_spacing: float = 1.15
    overflow: str = "shrink"
    min_size: int = 14
    max_lines: int = 0


# ---------------------------------------------------------------- 校验
@lru_cache(maxsize=1)
def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_template(data: dict) -> None:
    """schema + 语义校验；失败抛 TemplateError。"""
    if not isinstance(data, dict):
        raise TemplateError("模板必须是 JSON 对象")

    errs = minischema.validate(data, _schema())
    if errs:
        raise TemplateError("模板 schema 校验失败：\n  - " + "\n  - ".join(errs))

    canvas = data["canvas"]
    cw, ch = int(canvas["width"]), int(canvas["height"])

    cols = data["columns"]
    for name, c in cols.items():
        if not (0 <= c["x0"] < c["x1"] <= cw):
            raise TemplateError(f"列 {name} 的 x 边界越界或逆序：{c}（画布宽 {cw}）")

    per_page = int(data["perPage"])
    cuts = data["rows"]["cuts"]
    if len(cuts) != per_page:
        raise TemplateError(f"rows.cuts 行数 {len(cuts)} != perPage {per_page}")

    header = data["rows"]["header"]
    if not (0 <= header["y0"] < header["y1"] <= ch):
        raise TemplateError(f"表头行 y 越界：{header}")
    prev = header["y1"] - 1
    for i, r in enumerate(cuts):
        if not (0 <= r["y0"] < r["y1"] <= ch):
            raise TemplateError(f"第 {i + 1} 行 y 越界：{r}")
        if r["y0"] < prev:
            raise TemplateError(f"第 {i + 1} 行与上一行重叠：{r}")
        prev = r["y1"]

    # picture 列宽必须为正
    pic = cols["picture"]
    if pic["x1"] - pic["x0"] <= 0:
        raise TemplateError("picture 列宽必须为正")

    default_font = data["fonts"].get("default")
    if not default_font:
        raise TemplateError("缺少 fonts.default")


# ---------------------------------------------------------------- 模板对象
@dataclass
class Template:
    data: dict
    path: Path | None = None

    # ---- 基本属性 ----
    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def canvas_w(self) -> int:
        return int(self.data["canvas"]["width"])

    @property
    def canvas_h(self) -> int:
        return int(self.data["canvas"]["height"])

    @property
    def canvas(self) -> tuple[int, int]:
        return (self.canvas_w, self.canvas_h)

    @property
    def dpi(self) -> int:
        return int(self.data["canvas"]["dpi"])

    @property
    def per_page(self) -> int:
        return int(self.data["perPage"])

    @property
    def base_psd(self) -> str | None:
        return self.data.get("basePsd")

    @property
    def columns(self) -> dict[str, Column]:
        return {k: Column(int(v["x0"]), int(v["x1"])) for k, v in self.data["columns"].items()}

    def column(self, name: str) -> Column:
        return self.columns[name]

    @property
    def header(self) -> Band:
        h = self.data["rows"]["header"]
        return Band(int(h["y0"]), int(h["y1"]))

    @property
    def rows(self) -> list[Row]:
        return [Row(i, int(r["y0"]), int(r["y1"]))
                for i, r in enumerate(self.data["rows"]["cuts"])]

    def row(self, index: int) -> Row:
        return self.rows[index]

    @property
    def decorations(self) -> dict:
        return self.data["decorations"]

    @property
    def picture(self) -> dict:
        return self.data["picture"]

    @property
    def text(self) -> dict:
        return self.data["text"]

    # ---- 字体 ----
    def font(self, name: str = "default") -> FontSpec:
        fonts = self.data["fonts"]
        default = fonts["default"]
        spec = fonts.get(name) or default
        return FontSpec(
            family=str(spec.get("family", default["family"])),
            size=int(spec.get("size", default["size"])),
            bold=bool(spec.get("bold", False)),
            line_spacing=float(spec.get("lineSpacing", default.get("lineSpacing", 1.15))),
            overflow=str(spec.get("overflow", default.get("overflow", "shrink"))),
            min_size=int(spec.get("minSize", self.data["text"].get("minSize", 14))),
            max_lines=int(spec.get("maxLines", 0)),
        )

    # ---- 便捷框 ----
    def picture_box(self, row: Row) -> tuple[int, int, int, int]:
        c = self.columns["picture"]
        return (c.x0, row.y0, c.x1, row.y1)

    def cell_box(self, column: str, row: Row) -> tuple[int, int, int, int]:
        c = self.columns[column]
        return (c.x0, row.y0, c.x1, row.y1)

    # ---- 竖直分隔线 x（由列边界去重推导，用于兜底底版网格）----
    def vertical_boundaries(self) -> list[int]:
        xs = set()
        for c in self.columns.values():
            xs.add(c.x0)
            xs.add(c.x1)
        return sorted(xs)


def from_dict(data: dict, path: Path | None = None) -> Template:
    validate_template(data)
    return Template(data=data, path=path)


def load_template(path: str | Path | None = None) -> Template:
    p = Path(path) if path is not None else DEFAULT_TEMPLATE_PATH
    if not p.exists():
        raise TemplateError(f"模板文件不存在：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return from_dict(data, path=p)


@lru_cache(maxsize=8)
def _load_cached(path_str: str) -> Template:
    return load_template(path_str)


def default_template() -> Template:
    return _load_cached(str(DEFAULT_TEMPLATE_PATH))


def coerce_template(obj: "Template | dict | str | Path | None" = None) -> Template:
    """把 None/Template/dict/路径/模板 id 统一成 Template。"""
    if obj is None:
        return default_template()
    if isinstance(obj, Template):
        return obj
    if isinstance(obj, dict):
        return from_dict(obj)
    s = str(obj)
    p = Path(s)
    if p.exists():
        return load_template(p)
    cand = TEMPLATE_DIR / f"{s}.json"
    if cand.exists():
        return load_template(cand)
    raise TemplateError(f"找不到模板：{s}（既非文件，也不是 templates/*.json 的 id）")


# ---------------------------------------------------------------- 分页
def paginate(cuts: list, per_page: int = 5) -> list[list]:
    """按顺序每页切 per_page 个 cut。"""
    per_page = max(1, int(per_page))
    return [cuts[i:i + per_page] for i in range(0, len(cuts), per_page)]
