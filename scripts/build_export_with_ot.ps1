# SPDX-License-Identifier: BSD-3-Clause
# 用已安装的 OpenToonz 构建环境编译 konte-export（KONTE_WITH_OPENTOONZ），并生成真实 .tnz。
# 前置：Qt5.15 / OpenCV / Boost / MSVC 就绪（见 docs/BUILD_ENV_WINDOWS.md）。
param(
  [string]$QtPath    = "X:\agent\tools\Qt\5.15.2\msvc2019_64",
  [string]$OpenCVDir = "X:\agent\tools\opencv\opencv\build\x64\vc16\lib",
  [string]$BoostRoot = "",
  [string]$BuildDir  = "X:\agent\build\opentoonz",
  [string]$ScenePlans = "",
  [string]$OutDir     = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $BoostRoot) { $BoostRoot = "$repo\toonz\thirdparty\boost\boost_1_73_0" }
if (-not $ScenePlans) { $ScenePlans = "$repo\poc\examples\EP01\out\scenes" }
if (-not $OutDir) { $OutDir = "$repo\poc\examples\EP01\out\tnz" }

# 1) 幂等注入"konte 导出内核"集成钩子到 OT sources CMakeLists（不改上游逻辑）
$cm = "$repo\toonz\toonz\sources\CMakeLists.txt"
$enc = New-Object System.Text.UTF8Encoding($false)
$t = [IO.File]::ReadAllText($cm, [Text.Encoding]::UTF8)
if ($t -notmatch 'KONTE_BUILD_EXPORT_KERNEL') {
  $block = @'

# ===== konte-core export kernel (Repo1 P1 integration) =====
option(KONTE_BUILD_EXPORT_KERNEL "Build konte-core export kernel (konte-export)" OFF)
if(KONTE_BUILD_EXPORT_KERNEL)
  set(KONTE_WITH_OPENTOONZ ON CACHE BOOL "" FORCE)
  add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../../../konte-core" "${CMAKE_BINARY_DIR}/konte-core")
endif()
'@
  [IO.File]::WriteAllText($cm, $t + $block, $enc)
  Write-Host "[hook] appended konte integration block"
}

# 2) 配置（VS2022 x64）
$otSources = "$repo\toonz\toonz\sources"
cmake -S $otSources -B $BuildDir -G "Visual Studio 17 2022" -A x64 `
  -DQT_PATH="$QtPath" -DOpenCV_DIR="$OpenCVDir" -DOpenCV_RUNTIME=vc16 `
  -DBOOST_ROOT="$BoostRoot" -DBoost_INCLUDE_DIR="$BoostRoot" `
  -DWITH_TRANSLATION=OFF -DWITH_WINTAB=OFF -DKONTE_BUILD_EXPORT_KERNEL=ON
if ($LASTEXITCODE -ne 0) { throw "configure failed" }

# 3) 构建 konte-export（自动带出 toonzlib/image 等依赖）
cmake --build $BuildDir --config Release --target konte-export -- /m:4
if ($LASTEXITCODE -ne 0) { throw "build failed" }

# 4) 运行（设置运行时 DLL 搜索路径）
$tp = "$repo\toonz\thirdparty"
$env:TOONZROOT = "$repo\toonz\stuff"
$env:PATH = @(
  "$BuildDir\Release",
  "$QtPath\bin",
  "X:\agent\tools\opencv\opencv\build\x64\vc16\bin",
  "$tp\libmypaint\dist\64", "$tp\glew\glew-1.9.0\bin\64bit", "$tp\glut\3.7.6\lib",
  $env:PATH
) -join ';'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
& "$BuildDir\Release\konte-export.exe" --sceneplans $ScenePlans --out $OutDir
Write-Host ("konte-export exit=" + $LASTEXITCODE)
