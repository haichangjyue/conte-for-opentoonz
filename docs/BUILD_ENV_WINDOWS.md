# Windows 构建环境（OpenToonz 导出内核）

> 记录 2026-11-12 在本机搭建并**验证通过**的 OpenToonz 构建环境，供复现 P1。
> 目标：以 `KONTE_WITH_OPENTOONZ` 构建 `konte-export`，用 ScenePlan 生成真实 `.tnz`。

## 安装位置与版本（实测）

| 组件 | 版本 | 路径 |
|---|---|---|
| MSVC / VS Build Tools | 19.44 (VS2022, vc143) | `X:\agent\tools\vsbuild` |
| Windows SDK | 10.0.22621 | `C:\Program Files (x86)\Windows Kits\10` |
| CMake | 4.4.4 | `C:\Program Files\CMake` |
| Qt | 5.15.2 msvc2019_64 **+ QtScript（源码构建）** | `X:\agent\tools\Qt\5.15.2\msvc2019_64` |
| OpenCV | 4.8.0（vc16 预编译） | `X:\agent\tools\opencv\opencv\build` |
| Boost | 1.73.0（仅头文件） | `toonz\thirdparty\boost\boost_1_73_0` |

## 关键步骤（踩坑记录）

1. **Qt**：用 `aqtinstall` 装 5.15.2 msvc2019_64（qtbase/qtsvg/qtmultimedia/qtserialport/qttools/qtimageformats）。
   - 官方预编译包**不含 QtScript**，而 `toonzlib` 强依赖 `Qt5::Script`。
   - 解决：从源码构建 qtscript v5.15.2（需 `perl`，用 `C:\Program Files\Git\usr\bin\perl.exe`），
     `qmake && nmake && nmake install` 装入同一 Qt 目录（会生成 `lib/cmake/Qt5Script*`）。
2. **OpenCV**：预编译包为 vc16（VS2019）。MSVC 19.44 不被 `OpenCVConfig` 识别 →
   `-DOpenCV_DIR=.../build/x64/vc16/lib -DOpenCV_RUNTIME=vc16`（vc16 与 vc143 ABI 兼容）。
3. **Boost**：仅需头文件；解压 `boost_1_73_0` 到 `toonz\thirdparty\boost\`（避免并发解压造成残缺）。
4. **配置**：
   ```powershell
   cmake -S toonz\toonz\sources -B X:\agent\build\opentoonz -G "Visual Studio 17 2022" -A x64 `
     -DQT_PATH="X:\agent\tools\Qt\5.15.2\msvc2019_64" `
     -DOpenCV_DIR="X:\agent\tools\opencv\opencv\build\x64\vc16\lib" -DOpenCV_RUNTIME=vc16 `
     -DBOOST_ROOT="<repo>\toonz\thirdparty\boost\boost_1_73_0" `
     -DBoost_INCLUDE_DIR="<repo>\toonz\thirdparty\boost\boost_1_73_0" `
     -DWITH_TRANSLATION=OFF -DWITH_WINTAB=OFF -DKONTE_BUILD_EXPORT_KERNEL=ON
   ```
5. **构建**：`cmake --build X:\agent\build\opentoonz --config Release --target konte-export -- /m:4`
   （会先构建 tnzcore/tnzbase/tnzext/toonzlib/image）。
6. **运行**：需把 `Release`、Qt `bin`、OpenCV `bin`、`thirdparty` 各 DLL 目录加入 PATH，并设 `TOONZROOT=<repo>\toonz\stuff`。

## 已知问题与处理

- **图像 IO 未初始化**：`loadLevel` 对 png 返回 0 → 需 `Tiio::defineStd(); initImageIo();`（已在 `ot_scene_writer.cpp` 调用）。
- **`ToonzScene::save` 仅留下 `<file>.tmp`** 未完成 replace（本环境实测）→ 内核在保存后检测并完成 `.tmp → .tnz` 改名兜底。
- **参考层路径（已解决）**：`.tnz` 内记录 **`$scenefolder/<stem>.0001.png`**（参考图存为带帧号的 `.0001.png`）。裸相对名或**无帧号文件名**会导致 OT 重载时 level 帧号为 `NO_FRAME(-2)`、与单元格 `0001` 不匹配 → 空白层。
- **绝不要污染用户 OT 配置**：导出进程需在**进程内**用 `TEnv::setArgPathValue("TOONZPROFILES"/"TOONZCONFIG"/..., <临时目录>)` 覆盖路径（Windows 下 TEnv 只读注册表、不读环境变量）。否则运行导出会改写用户 `profiles/.../preferences.ini`，实测会把界面语言重置为 English。`konte-export` 已内置该隔离；`package.py` 也会传入隔离环境。
- **音频**：`cut.audio.path` → ScenePlan.sound → `TXshSoundLevel`+`TXshSoundColumn`；声音列必须建成**单个连续 ColumnLevel（0..N-1）**。多个重叠 `SoundCells` 会触发 OT 关闭时 `TSoundOutputDevice::isPlaying` 访问崩溃。演示工程 EP01 已为每个 cut 附带 `audio/*.wav`。**`cut.audio.offsetFrames`** 会让声音列从该偏移帧开始（起点前留空），实测 `.tnz` SoundCells 起点由 0 变为 12。
- **模板**：`--template` 以模板 `.tnz` 为底，**保留模板全部图层（columns）**，仅清空模板 notes；模板层超长裁到 N、单帧静态层 hold 到 N；本 cut 参考层作为新列追加。实测模板 1280×720 生效、每 cut 两列。模板文件须为无 BOM、OT 可解析的 `.tnz`。
- **参考层只读**：导出后把参考 PNG 置为只读；OT 重载时据此判定 level 只读（`.tnz` 本身不序列化该标志）。
- **QtScript 源码构建需要 perl**：用 Git 自带 perl。

## 集成钩子（可提交 patch）

OT `toonz/sources/CMakeLists.txt` 末尾需要一个**可选**的 konte 导出内核子目录钩子（默认 OFF）：

```powershell
cd repos\konte-for-opentoonz\toonz
git apply ..\patches\opentoonz-konte-hook.patch     # 应用（可 -R 回滚）
```

- patch 见 [`patches/opentoonz-konte-hook.patch`](../patches/opentoonz-konte-hook.patch)：
  仅在 `-DKONTE_BUILD_EXPORT_KERNEL=ON` 时 `add_subdirectory(../../../konte-core)`，不改上游逻辑。
- `scripts/build_export_with_ot.ps1` 已改为**优先应用该 patch**（失败回退到幂等字符串追加）。
- 应用后主仓 `git status` 显示 submodule `toonz` dirty 属预期；commit 基线为 upstream `a250456…`。

## 一键脚本

```powershell
pwsh -File scripts\build_export_with_ot.ps1
```

## 验证结果（2026-11-12）

- 7 个 cut（含 1 个超框）全部生成 `.tnz`；
- 回读 `loadFrameCount` 与 `duration.totalFrames` **逐一相等**（72/36/48/18/102/60/72）；
- `.tnz` 头：`<tnz framecount="72" version="71.1">`，相机 1920×1080 16:9，参考层 PNG，ACTION/DIALOGUE 注记写入成功。
