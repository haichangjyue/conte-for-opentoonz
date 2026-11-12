# konte-format （【开】数据标准）

- `konte.schema.json`：分镜项目数据（cut 为中心，单一事实源）
- `manifest.schema.json`：导出产物清单
- `pdf-template.schema.json`：分镜 PDF 版式模板（P4，坐标外部化）
- `templates/`：可直接用的版式模板
  - `scfilms_storyboard.json`：A4·5-cut 基准（scfilms StoryBoard.psd @300dpi）
  - `scfilms_storyboard_4cut.json`：A4·4-cut 变体（多模板验证）
- `fonts/`：随包 CJK 字体落点 + 许可证（SIL OFL 1.1）+ `fonts.json` 映射

规范文档建议 CC-BY-4.0；JSON Schema 可自由采用。

## 模板用法

```powershell
# 列出模板
python -m konte_poc templates
# 用指定模板导出（换底版 PSD = 换模板 JSON）
python -m konte_poc export examples\EP01\konte.json --out out `
  --pdf-template konte-format\templates\scfilms_storyboard_4cut.json
```

模板结构见 `pdf-template.schema.json`：`canvas` / `columns` / `rows` / `decorations` /
`picture`(inset/mode/oversizeMode/bleedIndicator) / `fonts`(family/size/lineSpacing/overflow/minSize/maxLines) /
`text`(pad/align/valign/kinsoku)。字体族见 `fonts/README.md`。

## 一镜跨多格（真实分镜）

`konte.schema.json` 的 cut 支持可选 `layout: { page, rowStart, rowSpan }`：真实社内分镜允许一个镜头占多个格子
（用于展开表演/多张画面）。`drawings[]` 按行依次放入这些格子；PDF 导出时 CUT 贴块顶、Dur 贴块底、文字跨整块。
`poc/tools/import_storyboard_tif.py` 可从整页 TIF 自动推断该 layout 并重建 konte.json。

