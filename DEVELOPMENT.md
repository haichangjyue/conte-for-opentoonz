# 开发启动说明（DEVELOPMENT）

> 状态：**v0.1 开发启动（2026-11-12）**。依据《工程交接技术规格 v1.0》启动 PoC 优先的工程实现。
> 本文件说明"现在能跑什么、怎么跑、下一步做什么"，给工程团队接续。

## 0. 我们做了什么（首个里程碑）

把交接包里**可在此环境独立验证**的主线先跑通，作为 C++ 导出内核的对拍基准：

1. **`konte-core` PoC（Python，`poc/`）**
   - `konte.json` 校验（JSON Schema 2020-12 子集 + 业务不变量）
   - 决定稿闸门（`final` + 无 TBD）
   - 秒+帧 → 帧数换算与校验
   - **A4·5-cut 分镜 PDF**：直接以 `scfilms_StoryBoard.psd` 为空白底版、按实测坐标叠图（Q4/P4）→ 视觉一致、可直接打印
   - 每 cut **渲染参考图**（Q8）+ **ScenePlan**（`.tnz` 输入契约）+ **manifest.json**
2. **Bridge sidecar（Python，`bridge/src/konte_bridge/`）**
   - OpenAPI 9 条路径 + `/ws` 事件推送，PIN/token、cut 锁、画面上传→缩略图、导出任务
3. **测试**：PoC 48 项 + Bridge(Python) 16 项 + Qt Bridge 6 项，全绿。

> 已交付示例：`poc/examples/EP01/out/storyboard.pdf`（2 页 A4）、`manifest.json`、7 张参考图、7 份 ScenePlan。

## 1. 快速开始

```powershell
$py = "C:\Users\haichangjyue\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
cd poc; $env:PYTHONPATH = (Get-Location).Path

& $py tools\make_demo.py
& $py -m konte_poc export examples\EP01\konte.json --out examples\EP01\out `
   --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"
& $py -m unittest discover -s tests -v
```

或直接用 `scripts/run_demo.ps1`（自动找 Python、生成+导出+预览）。

### 端到端交付打包（PDF + 真实 .tnz + 参考图 + manifest + zip）
```powershell
pwsh -File scripts/package_deliverable.ps1 -OutRoot "X:\agent\build\deliverables"
# 产物：<OutRoot>\EP01\{scenes/*.tnz+ref, references/*.png, storyboard.pdf, manifest.json, DELIVERY.md} + EP01.zip
```

## 2. 与规格的对应

| 规格条目 | 落点 | 状态 |
|---|---|---|
| §2 数据契约 / konte.schema.json | `poc/konte_poc/model.py`, `minischema.py` | ✅ |
| Q1 决定稿闸门 | `model.check_export_gate` / Bridge 422 | ✅ |
| Q4 A4·5-cut PDF 叠图 | `poc/konte_poc/pdfgen.py` | ✅（P4 通过） |
| Q8 渲染位图参考层 | `render.render_reference`, ScenePlan `level.lock` | ✅ |
| §5 导出内核 `.tnz` | `konte-core/`（C++：ScenePlan→.tnz，`KONTE_WITH_OPENTOONZ`） | ✅ 运行验证：7/7 真实 .tnz，帧数回读一致 |
| §3 Bridge API | `bridge/src/konte_bridge/` | ✅（参考实现） |
| §5.3 打包 | `package.py` / `scripts/package_deliverable.ps1`（tnz+refs+PDF+manifest+zip+校验） | ✅ 端到端 |
| §8 PoC P1（OT 无头生成 .tnz） | 需 OpenToonz 源码与构建环境 | ⏳ 见下 |

## 3. 下一步（按 PoC 优先级）

1. **P1｜OT 无头生成 `.tnz`（关键路径）** — ✅ 运行验证通过
   - ✅ OpenToonz 源码接入 `toonz/`（浅克隆 submodule）。
   - ✅ `konte-core/` C++ 内核 + `konte-export`（真实 OT API），Windows 环境构建成功。
   - ✅ 7/7 cut 生成真实 `.tnz`，`loadFrameCount` 与时长帧数逐一相等；参考层/Note 写入正确。
   - ✅ 参考层锁定（`setIsReadOnly` + 参考 PNG 只读）、声音列（`TXshSoundColumn`，验证 cut sounds=1）、
     `loadTnzFile` 重载校验通过。
   - ✅ 模板 `.tnz` 套用：**保留全部模板图层**（超长裁到 N、单帧静态层 hold 到 N），仅清空模板 notes；实测 1280×720 生效。参考层相对 `$scenefolder` 打包（无绝对路径）。
2. **P2｜端到端交付打包** — ✅ 完成
   - `konte_poc package` / `scripts/package_deliverable.ps1`：Python（参考图/PDF/manifest/ScenePlan）+ C++（`.tnz`）
     汇成交付目录；参考层相对引用；含 `DELIVERY.md` 与 `manifest` 校验；自动 zip。
   - 实测 EP01：7 `.tnz` + 7 参考图 + `storyboard.pdf` + `manifest.json` → `EP01.zip`（0.68MB），verify 全 OK。
3. **P4 收尾** — ✅ 完成
   - 模板多套坐标配置：`konte-format/templates/*.json` + `pdf-template.schema.json`；`pdfgen` 改为模板驱动（换底版=换模板）。
   - 字体授权锁定：默认 **Source Han Sans（思源黑体，SIL OFL 1.1）**，随包 `konte-format/fonts/`（OFL 全文 + fonts.json）。
   - PDF 视觉精修：长台词 shrink/ellipsis 溢出、日文禁则换行、超框 cover 裁切/bleed 虚线提示；多模板（4-cut 变体）实测。
4. **P5｜批量导出 / 断点续 / 进度日志** — ✅ 完成
   - `konte_poc batch`：`_export_state.json` 断点续、`export_log.jsonl` 进度、`batch_report.json` 失败汇总；只对增量 ScenePlan 调内核。
   - 实测：250 cut 结构包二次全复用（内核零调用）；真实内核 7 cut 首跑 7/7、二次 0.02s 全复用。
5. **打包增强** — ✅ 完成：manifest 音频字段、`--no-audio`、`--zip-name`；含音频/静音包均 verify ok。
6. **Bridge 生产化** — ✅ Python 加固完成（token TTL/PIN 锁定/上传限速/锁 TTL/任务保留/health）；
   ✅ Qt5 原生内嵌服务 `bridge-qt/`（QTcpServer + 手写 WS，含 multipart 图片上传/缩略图、export、WS 广播）。
7. **P5 强化** — ✅ 流式/分卷 PDF（`pdfstream.py`，>8 页自动流式，250 cut/50 页实测）；✅ 音频 `offsetFrames` 内核落地；
   ⏳ 声音切片边界、导出并发、多音轨/混音。
8. **OT 构建可复现** — ✅ 集成钩子做成 `patches/opentoonz-konte-hook.patch`（可提交/回滚，构建脚本优先应用）。
9. **真实分镜试产** — ✅ 支持「一镜跨多格」`cut.layout`；`import_storyboard_tif.py` 从真实整页 TIF 自动推断跨格并重建 konte.json；
   实测 2 页真实分镜（5 cut，页合计 14+16 / 8+0 与原图一致），已扩到 7 页/22 cut 并验收通过。
10. **编辑器 Web MVP（轻量草图）** — ✅ `repos/konte-studio/web/`：配对→项目/镜头（按页分组+缩略图）→文字/时长→画笔/橡皮/撤销/描摹/导入→保存画面→导出；
    平板触控/压感/响应式 + 上一镜/下一镜快捷键；Edge headless E2E（桌面 + CDP Touch 横/竖屏）在 Python/Qt Bridge 均跑通。完整绘制引擎不在 MVP（原画用 OT）。

## 4. 边界与约束（不漂移）

- **Web 永不产交付物**；交付只由 OT 导出内核生成（本轮 PoC 是内核的"预演/对拍"，不是 Web 侧交付）。
- **开源边界（D9）**：`poc/`、`bridge/`、`konte-format/`、`KERNEL_CONTRACT.md` 属 Repo1（BSD-3）；
  编辑器 UX/Web/云属 Repo2（专有）。见 `../仓库结构与开源边界.md`。
- **数据以 `konte.schema.json` 为界**：编辑器写它、内核读它。

## 5. 依赖

- Python 3.10+；**Pillow**（图像/PDF）。PoC 其余为 stdlib（`http.server`、`json`、`socket`）。
- 字体：默认 **Source Han Sans（思源黑体，SIL OFL 1.1）**（覆盖中日混排）；模板 `fonts.*.family` 可指定字体族，
  可用 `KONTE_FONT` 指定单个字体文件；随包字体/许可证见 `konte-format/fonts/`。
