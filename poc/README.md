# konte-core PoC（Python 参考实现）

> 定位：`konte-core` 的**可独立运行的 PoC/对拍基准**。用零第三方依赖（仅 Pillow）先把
> **数据契约 + 决定稿闸门 + A4·5-cut PDF（P4）+ 参考图 + manifest + ScenePlan** 跑通，
> 供后续 C++ 导出内核（P1 `.tnz`）对齐行为。
> 真正的 `.tnz` 由 OpenToonz C++ 内核生成，见仓库根 `KERNEL_CONTRACT.md`。

## 能做什么

| 能力 | 对应规格 | 状态 |
|---|---|---|
| `konte.json` 校验（JSON Schema 2020-12 子集 + 业务不变量） | 数据契约 §2.1 | ✅ |
| 决定稿闸门（`status=final` 且无 TBD） | 铁律 1 / `blockUntilResolved` | ✅ |
| 时长「秒+帧 → 帧数」换算与校验 | §2.1 | ✅ |
| **A4 分镜 PDF（PSD 叠图）** | Q4 / P4 | ✅ 真实底版 + **模板坐标外部化**（多模板/字体/overflow/bleed） |
| 每 cut 渲染参考图（Q8 位图参考层） | Q8 | ✅ |
| 每 cut `ScenePlan`（`.tnz` 生成输入契约） | §5.1 | ✅ |
| `manifest.json`（产物清单） | §2.2 | ✅ |
| **批量导出（断点续/进度 JSONL/失败汇总，>200 cut）** | P5 | ✅ |
| **真实分镜 TIF 导入（一镜跨多格 layout）** | P5+ | ✅ |
| `.tnz` 场景落盘 | §5.1 / P1 | ⏳ 需 OT C++ 内核 |

## 目录

```
poc/
├─ konte_poc/
│  ├─ minischema.py   # 零依赖 JSON Schema 子集校验器
│  ├─ model.py        # 载入/不变量/闸门/时长/寻址
│  ├─ template.py     # PDF 版式模板（坐标外部化 + 校验，P4）
│  ├─ layout.py       # 旧版坐标常量（兼容 shim，已改为从模板推导）
│  ├─ textfit.py      # CJK 字体族/换行/禁则/溢出策略
│  ├─ render.py       # 参考图 + 图片贴合（contain/cover/bleed）
│  ├─ pdfgen.py       # 叠图法生成 PDF（模板驱动，自动流式）
│  ├─ pdfstream.py    # 逐页流式多页 PDF（Flate 无损，O(1 页) 内存）
│  ├─ scene_plan.py   # ScenePlan（.tnz 输入契约）
│  ├─ manifest.py     # 产物清单
│  ├─ export.py       # 导出编排
│  ├─ batch.py        # 批量导出（断点续/进度/失败汇总，P5）
│  └─ cli.py          # 命令行（含 templates / batch 子命令）
├─ tools/
│  ├─ make_demo.py    # 生成示例项目（konte.json + 模拟画面）
│  ├─ import_storyboard_tif.py # 真实整页 TIF → 跨格 konte.json（自动切画面）
│  ├─ tif_pages_to_pdf.py      # 真实整页 TIF → A4 PDF（保真）
│  └─ preview_pages.py# 页面 PNG 预览 + PDF 自检
├─ tests/             # unittest（48 项）
└─ examples/EP01/     # 示例项目与示例交付物 out/
```

## 快速开始

```powershell
# 需 Python 3.10+ 与 Pillow；本仓库随附运行时可直接用
cd poc
$env:PYTHONPATH = (Get-Location).Path

# 1) 生成示例项目（konte.json + panels/*.png）
python tools/make_demo.py

# 2) 校验
python -m konte_poc validate examples\EP01\konte.json

# 3) 导出（真实 PSD 底版 → A4 分镜 PDF + 参考图 + ScenePlan + manifest）
python -m konte_poc export examples\EP01\konte.json --out examples\EP01\out `
  --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"

# 3b) 换模板（多模板/换底版 = 换一个模板 JSON）
python -m konte_poc templates
python -m konte_poc export examples\EP01\konte.json --out examples\EP01\out_4cut `
  --pdf-template ..\konte-format\templates\scfilms_storyboard_4cut.json

# 4) 测试
python -m unittest discover -s tests -v

# 5) 端到端交付打包（Python 参考图/PDF + C++ .tnz + manifest + zip）
python -m konte_poc package examples\EP01\konte.json --out-root "X:\agent\build\deliverables" `
  --exporter "X:\agent\build\opentoonz\Release\konte-export.exe" `
  --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"
#    可选：--no-audio（剔除音频）、--zip-name EP01_v1.2（zip 版本命名）

# 6) 真实整页分镜 TIF → 结构化 konte.json（一镜跨多格）+ 导出
python tools\import_storyboard_tif.py --out examples\SK01 --pages 01.tif 02.tif `
  --sidecar examples\SK01\tif_texts.json --fps 24 --title SK01
python -m konte_poc export examples\SK01\konte.json --out examples\SK01\out `
  --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"
# 或仅保真转 A4 PDF：python tools\tif_pages_to_pdf.py out.pdf 01.tif 02.tif

# 7) 批量导出（断点续 + 进度日志；>8 页自动流式 PDF）
python -m konte_poc batch examples\EP01\konte.json --out "X:\agent\build\batch" `
  --exporter "X:\agent\build\opentoonz\Release\konte-export.exe" `
  --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd" --quiet
# 产物：scenes/*.tnz+ref+sceneplan、references/、storyboard.pdf、manifest.json、
#       _export_state.json（断点续状态）、export_log.jsonl（进度日志）、batch_report.json
```

## 设计要点（对齐领域与规格）

- **单一事实源**：只读 `konte.json`；导出产物全部可由决定稿重生成。
- **决定稿闸门**：`draft` 或存在 `tbd` 时长 → 拒绝导出（`ExportGateError`，Bridge 映射 422）。
- **叠图不重绘**（Q4）：直接用 `scfilms_StoryBoard.psd` 合成为空白底版，按模板坐标叠加；
  **换模板 = 换一份 `konte-format/templates/*.json`**（换底版 PSD 只改 `basePsd`/坐标）。
- **每页 N cut**：行数与分页来自模板 `perPage`/`rows`（默认 5，变体 4）。
- **字体授权**：默认 **Source Han Sans（思源黑体）**（SIL OFL 1.1，覆盖中日混排）；模板 `fonts.*` 可指定
  字体族/字号/行距/溢出策略（shrink/truncate/ellipsis），见 `konte-format/fonts/`。
- **参考层锁定**（Q8）：参考图为位图，ScenePlan 标记 `level.lock=true`。
- **时长为秒+帧**（日式 24fps）：`totalFrames == seconds*fps + frames`。

## 已知边界 / 下一步

- `.tnz` 未在此生成（需 OT 运行时）；ScenePlan 已是 C++ 内核的完整输入契约。
- 字体默认用 **Source Han Sans**（思源黑体；备选 Noto Sans SC/JP、msyh、MS Gothic）；发布前按 `LICENSES.md` §5 随包附
  `konte-format/fonts/`（字体 + OFL 许可证）；可用环境变量 `KONTE_FONT` 指定单个字体文件。
- 语音/音效切片、Note 列写入的具体 OT API 待 P1 PoC 验证（见 `KERNEL_CONTRACT.md`）。
