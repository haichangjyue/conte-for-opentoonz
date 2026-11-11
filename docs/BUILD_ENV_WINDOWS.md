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
- **参考层路径**：当前 `.tnz` 内记录为绝对路径；正式打包需 OT 的 Export Scene / 资源收集改为相对 `$scenefolder`（P2 打包阶段处理）。
- **QtScript 源码构建需要 perl**：用 Git 自带 perl。

## 一键脚本

```powershell
pwsh -File scripts\build_export_with_ot.ps1
```

## 验证结果（2026-11-12）

- 7 个 cut（含 1 个超框）全部生成 `.tnz`；
- 回读 `loadFrameCount` 与 `duration.totalFrames` **逐一相等**（72/36/48/18/102/60/72）；
- `.tnz` 头：`<tnz framecount="72" version="71.1">`，相机 1920×1080 16:9，参考层 PNG，ACTION/DIALOGUE 注记写入成功。
