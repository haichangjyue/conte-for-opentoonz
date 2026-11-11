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
3. **测试**：PoC 16 项 + Bridge 9 项，全绿。

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

## 2. 与规格的对应

| 规格条目 | 落点 | 状态 |
|---|---|---|
| §2 数据契约 / konte.schema.json | `poc/konte_poc/model.py`, `minischema.py` | ✅ |
| Q1 决定稿闸门 | `model.check_export_gate` / Bridge 422 | ✅ |
| Q4 A4·5-cut PDF 叠图 | `poc/konte_poc/pdfgen.py` | ✅（P4 通过） |
| Q8 渲染位图参考层 | `render.render_reference`, ScenePlan `level.lock` | ✅ |
| §5 导出内核 `.tnz` | `konte-core/`（C++：ScenePlan→.tnz，`KONTE_WITH_OPENTOONZ`） | ✅ 运行验证：7/7 真实 .tnz，帧数回读一致 |
| §3 Bridge API | `bridge/src/konte_bridge/` | ✅（参考实现） |
| §5.3 打包 | `export.py` 产物目录（scenes/references/manifest/pdf） | ✅（无 OT 依赖部分） |
| §8 PoC P1（OT 无头生成 .tnz） | 需 OpenToonz 源码与构建环境 | ⏳ 见下 |

## 3. 下一步（按 PoC 优先级）

1. **P1｜OT 无头生成 `.tnz`（关键路径）** — ✅ 运行验证通过
   - ✅ OpenToonz 源码接入 `toonz/`（浅克隆 submodule）。
   - ✅ `konte-core/` C++ 内核 + `konte-export`（真实 OT API），Windows 环境构建成功。
   - ✅ 7/7 cut 生成真实 `.tnz`，`loadFrameCount` 与时长帧数逐一相等；参考层/Note 写入正确。
   - ⏳ 收尾：参考层只读锁定、声音切片、模板套用、打包改相对路径（`TODO(P1-runtime)`）。
2. **P4 收尾**：模板多套坐标配置（换 PSD）、字体授权锁定（Noto/Source Han）。
3. **P2 Bridge 生产化**：内嵌 `QTcpServer/QWebSocketServer` 或加固 sidecar 启动生命周期。
4. **P5 边界**：不同时长/超框/声音切片批量跑；>200 cut 性能与断点续。

## 4. 边界与约束（不漂移）

- **Web 永不产交付物**；交付只由 OT 导出内核生成（本轮 PoC 是内核的"预演/对拍"，不是 Web 侧交付）。
- **开源边界（D9）**：`poc/`、`bridge/`、`konte-format/`、`KERNEL_CONTRACT.md` 属 Repo1（BSD-3）；
  编辑器 UX/Web/云属 Repo2（专有）。见 `../仓库结构与开源边界.md`。
- **数据以 `konte.schema.json` 为界**：编辑器写它、内核读它。

## 5. 依赖

- Python 3.10+；**Pillow**（图像/PDF）。PoC 其余为 stdlib（`http.server`、`json`、`socket`）。
- 字体：默认取系统 CJK（msyh/Noto/MS Gothic）；可用 `KONTE_FONT` 指定。
