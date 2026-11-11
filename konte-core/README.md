# konte-core（【开】导出内核 & 格式库，BSD-3）

职责：把 `konte.json`（决定稿）归一出的 **ScenePlan** 导出为 OpenToonz `.tnz` 工程 + A4·5-cut PDF + manifest。
本目录是 **C++ 导出内核**；PDF/格式/校验的参考实现与对拍基准在 `../poc/`。

## 结构

```
konte-core/
├─ include/konte/
│  ├─ json.h           # 零依赖 JSON（解析/输出）
│  ├─ scene_plan.h     # ScenePlan 结构与校验
│  └─ export_kernel.h  # 导出内核接口
├─ src/
│  ├─ scene_plan.cpp
│  ├─ export_kernel.cpp     # 编排：校验→逐 cut→报告（OT 或 dry-run）
│  ├─ ot_scene_writer.cpp   # OpenToonz 写入（KONTE_WITH_OPENTOONZ 时编译）
│  └─ main.cpp              # CLI: konte-export
└─ tests/test_sceneplan.cpp
```

## 两种构建

```powershell
# A) 纯逻辑内核（无需 OT）：编译 + 跑测试
pwsh -File ../scripts/build_kernel.ps1

# B) 接入 OpenToonz（需先构建 OT，提供头/库）：
pwsh -File ../scripts/build_kernel.ps1 -WithOpenToonz `
  -OtIncludeDirs "C:\ot\toonz\sources\include;C:\ot\toonz\sources\toonz;..." `
  -OtLibs "toonzlib;tnzcore;tnzext;tpalette;..."
```

## 用法

```powershell
# dry-run：读 ScenePlan，校验并输出 .plan.txt + export_report.json（不依赖 OT）
.\build\kernel\konte-export.exe --sceneplans ..\poc\examples\EP01\out\scenes `
  --out ..\poc\examples\EP01\out\tnz --dry-run

# 真实导出（需 KONTE_WITH_OPENTOONZ 构建）：生成 .tnz
.\build\kernel\konte-export.exe --sceneplans ..\poc\examples\EP01\out\scenes `
  --out ..\poc\examples\EP01\out\tnz --template path\to\template.tnz
```

## 与 OpenToonz 的映射（真实 API）

`src/ot_scene_writer.cpp` 依据 `toonz/sources/include/toonz/*.h` 的真实签名实现：
`ToonzScene` / `TProjectManager::initializeScene` / `ToonzScene::loadLevel` /
`TXsheet::setCell` / `TXsheet::updateFrameCount` / `TXsheet::getNotes`(TXshNoteSet) / `ToonzScene::save`。
详见仓库根 `KERNEL_CONTRACT.md`。仍待运行时落地的点：参考层只读锁定、声音列切片（代码内 `TODO(P1-runtime)`）。
