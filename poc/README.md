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
| **A4·5-cut 分镜 PDF（PSD 叠图）** | Q4 / P4 | ✅ 真实底版 + 实测坐标 |
| 每 cut 渲染参考图（Q8 位图参考层） | Q8 | ✅ |
| 每 cut `ScenePlan`（`.tnz` 生成输入契约） | §5.1 | ✅ |
| `manifest.json`（产物清单） | §2.2 | ✅ |
| `.tnz` 场景落盘 | §5.1 / P1 | ⏳ 需 OT C++ 内核 |

## 目录

```
poc/
├─ konte_poc/
│  ├─ minischema.py   # 零依赖 JSON Schema 子集校验器
│  ├─ model.py        # 载入/不变量/闸门/时长/寻址
│  ├─ layout.py       # A4·5-cut 实测坐标与分页
│  ├─ textfit.py      # CJK 字体加载 + 换行 + 适配绘制
│  ├─ render.py       # 参考图 + 图片贴合
│  ├─ pdfgen.py       # 叠图法生成 PDF
│  ├─ scene_plan.py   # ScenePlan（.tnz 输入契约）
│  ├─ manifest.py     # 产物清单
│  ├─ export.py       # 导出编排
│  └─ cli.py          # 命令行
├─ tools/
│  ├─ make_demo.py    # 生成示例项目（konte.json + 模拟画面）
│  └─ preview_pages.py# 页面 PNG 预览 + PDF 自检
├─ tests/             # unittest（16 项）
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

# 3) 导出（真实 PSD 底版 → A4·5-cut PDF + 参考图 + ScenePlan + manifest）
python -m konte_poc export examples\EP01\konte.json --out examples\EP01\out `
  --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"

# 4) 测试
python -m unittest discover -s tests -v
```

## 设计要点（对齐领域与规格）

- **单一事实源**：只读 `konte.json`；导出产物全部可由决定稿重生成。
- **决定稿闸门**：`draft` 或存在 `tbd` 时长 → 拒绝导出（`ExportGateError`，Bridge 映射 422）。
- **叠图不重绘**（Q4）：直接用 `scfilms_StoryBoard.psd` 合成为空白底版，按实测坐标叠加；
  换模板 = 换一张底版 PSD。
- **每页 5 cut**：`layout.ROWS` 为实测 5 行；超出自动分页。
- **参考层锁定**（Q8）：参考图为位图，ScenePlan 标记 `level.lock=true`。
- **时长为秒+帧**（日式 24fps）：`totalFrames == seconds*fps + frames`。

## 已知边界 / 下一步

- `.tnz` 未在此生成（需 OT 运行时）；ScenePlan 已是 C++ 内核的完整输入契约。
- 字体默认用系统 CJK 字体（msyh / Noto / MS Gothic）；发布前须按 `LICENSES.md` 锁定可商用字体并随包。
- 语音/音效切片、Note 列写入的具体 OT API 待 P1 PoC 验证（见 `KERNEL_CONTRACT.md`）。
