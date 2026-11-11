# <PRODUCT NAME> — konte-for-opentoonz

> 一个**面向日本动画分镜（絵コンテ）的开源工具包**，基于 [OpenToonz](https://opentoonz.github.io/)。<br>
> An open-core storyboard (e-konte) toolkit based on OpenToonz.

[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

## 这是什么（What's open vs closed）

本仓库（Repo1）是 **open-core 的开源部分**，包含：

- ✅ **导出内核**：把分镜 cut 导出为 OpenToonz `.tnz` 工程 + A4·5-cut 分镜 PDF + 打包（`konte-core/`）
- ✅ **数据标准**：`konte.schema.json` / manifest schema（`konte-format/`）
- ✅ **Bridge API + sidecar 参考实现**：平板前端与 OT 协作的本地接口（`bridge/`）
- ✅ **OpenToonz 集成层**（导出命令接线等）

**不在本仓库**（属私有 Repo2，专有）：分镜编辑器 UX / Web 前端 / 云协作 / 企业功能。
→ 本仓库可**独立构建**出"OpenToonz + 导出/格式/Bridge 工具"的可用子集；完整产品由发行构建组合。

## 构建（Build）

```bash
git clone <this-repo> && cd konte-for-opentoonz
# 依赖 OpenToonz 构建环境（Qt/CMake/OpenCV/Boost 等，见 docs/）
cmake -S . -B build && cmake --build build --config Release
```
> 详细依赖与平台（Windows/macOS/Linux）见 `docs/` 与 OpenToonz 官方构建文档。

## PoC 快速开始（无需 OT 即可跑通的导出/格式主线）

`poc/` 是 `konte-core` 的 Python 参考实现（仅依赖 Pillow），先跑通
**数据校验 + 决定稿闸门 + A4·5-cut 分镜 PDF（PSD 叠图）+ 参考图 + manifest + ScenePlan**：

```powershell
cd poc; $env:PYTHONPATH=(Get-Location).Path
python tools\make_demo.py
python -m konte_poc export examples\EP01\konte.json --out examples\EP01\out --base-psd "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd"
python -m unittest discover -s tests -v
```

- 产物：`storyboard.pdf`（A4·5-cut）、`manifest.json`、`references/*.png`、`scenes/*.sceneplan.json`。
- `.tnz` 由 OpenToonz C++ 内核按 [`KERNEL_CONTRACT.md`](KERNEL_CONTRACT.md) 生成。
- 一键演示：`pwsh -File scripts/run_demo.ps1`。
- 开发状态与路线见 [`DEVELOPMENT.md`](DEVELOPMENT.md)。
- Bridge 本地服务（平板协作）见 [`bridge/README.md`](bridge/README.md)。

## 数据与接口
- 数据格式：`konte-format/konte.schema.json`（JSON Schema 2020-12）
- Bridge 契约：`bridge/bridge.openapi.yaml`（OpenAPI 3.0.3）

## 许可证（License）
- 本仓库：**BSD-3-Clause** — 见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
- 第三方与 OpenToonz 派生部分：见 [LICENSES.md](LICENSES.md)。
- **本项目为独立分支，非 OpenToonz 官方；未获 OpenToonz / DWANGO 背书。**

## 贡献 / Upstream
- 欢迎提交 issue / PR。
- 与上游的关系：本仓持续同步 `opentoonz/opentoonz`；**通用 bugfix 优先以小 PR 回馈上游**。
- 请为源文件加 SPDX 头：`// SPDX-License-Identifier: BSD-3-Clause`。

## 联系
<WEBSITE / EMAIL>
