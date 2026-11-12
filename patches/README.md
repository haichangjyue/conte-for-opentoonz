# patches —— OpenToonz 集成补丁（可提交）

`opentoonz-konte-hook.patch`：在 OpenToonz `toonz/sources/CMakeLists.txt` 末尾加入一个**可选**的
konte 导出内核子目录钩子（`KONTE_BUILD_EXPORT_KERNEL`，默认 OFF）。不改上游任何逻辑，只有显式
`-DKONTE_BUILD_EXPORT_KERNEL=ON` 时才 `add_subdirectory(../../../konte-core)`。

- 基线：upstream `opentoonz/opentoonz`（本仓库 `toonz/` 浅克隆，commit `a250456…`，nightly）。
- 目的：替代 `scripts/build_export_with_ot.ps1` 里"字符串追加"的临时做法，改为**可版本化、可 review、
  可回滚**的 patch。

## 应用 / 回滚（在 `toonz/` 子模块根目录执行）

```powershell
cd repos\konte-for-opentoonz\toonz
git apply ..\patches\opentoonz-konte-hook.patch          # 应用
git apply -R ..\patches\opentoonz-konte-hook.patch       # 回滚
```

`scripts/build_export_with_ot.ps1` 会**优先自动应用本 patch**（若尚未应用），失败才回退为幂等追加字符串。

## 说明

- 应用后主仓 `git status` 会显示 submodule `toonz` dirty，属预期（子模块工作区改动）。
- 该 patch 只改 CMake 入口；`konte-core/` 的源码在 Repo1 主仓，不在子模块内。
