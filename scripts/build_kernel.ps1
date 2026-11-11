# SPDX-License-Identifier: BSD-3-Clause
# 构建 konte-core 导出内核。
#  - 默认：构建“纯逻辑内核 + CLI + 测试”（无需 OpenToonz，clang++/g++ 即可），并跑 C++ 测试。
#  - 带 OT：用 CMake 配置 KONTE_WITH_OPENTOONZ=ON，并传入已构建的 OpenToonz 头/库。
#
# 用法：
#   pwsh -File scripts/build_kernel.ps1
#   pwsh -File scripts/build_kernel.ps1 -WithOpenToonz -OtIncludeDirs "C:\ot\include;..." -OtLibs "toonzlib;tnzcore;..."
param(
  [switch]$WithOpenToonz,
  [string]$OtIncludeDirs = "",
  [string]$OtLibs = "",
  [string]$Cxx = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$kc   = Join-Path $repo "konte-core"
$build = Join-Path $repo "build\kernel"
New-Item -ItemType Directory -Force -Path $build | Out-Null

function Find-Cxx {
  if ($Cxx) { return $Cxx }
  if ($env:KONTE_CXX) { return $env:KONTE_CXX }
  $cands = @(
    "C:\Users\haichangjyue\AppData\Local\Programs\Swift\Toolchains\6.4.2+Asserts\usr\bin\clang++.exe",
    "clang++", "g++"
  )
  foreach ($c in $cands) {
    if (Test-Path $c) { return $c }
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
  }
  throw "未找到 C++ 编译器；请安装 clang++/g++ 或用 -Cxx 指定"
}

if (-not $WithOpenToonz) {
  $cxx = Find-Cxx
  Write-Host "[konte-core] 编译器: $cxx" -ForegroundColor Cyan
  Push-Location $kc
  try {
    $src = @("src/scene_plan.cpp","src/export_kernel.cpp","src/ot_scene_writer.cpp")
    Write-Host "[1/2] 构建 konte-export.exe ..." -ForegroundColor Cyan
    & $cxx -std=c++17 -O2 -I include @src src/main.cpp -o (Join-Path $build "konte-export.exe")
    if ($LASTEXITCODE -ne 0) { throw "konte-export 构建失败" }
    Write-Host "[2/2] 构建并运行 C++ 测试 ..." -ForegroundColor Cyan
    & $cxx -std=c++17 -O2 -I include @src tests/test_sceneplan.cpp -o (Join-Path $build "konte_core_tests.exe")
    if ($LASTEXITCODE -ne 0) { throw "测试构建失败" }
    & (Join-Path $build "konte_core_tests.exe")
    if ($LASTEXITCODE -ne 0) { throw "C++ 测试未通过" }
    Write-Host "完成：$build\konte-export.exe" -ForegroundColor Green
  } finally { Pop-Location }
}
else {
  Write-Host "[konte-core] 使用 CMake + OpenToonz 构建" -ForegroundColor Cyan
  $inc = ($OtIncludeDirs -split ';' | Where-Object { $_ }) -join ';'
  $libs = ($OtLibs -split ';' | Where-Object { $_ }) -join ';'
  if (-not $inc) { throw "请用 -OtIncludeDirs 传入 OpenToonz 头目录（分号分隔）" }
  if (-not $libs) { throw "请用 -OtLibs 传入 OpenToonz 库（分号分隔）" }
  cmake -S $repo -B $build -DKONTE_WITH_OPENTOONZ=ON "-DKONTE_OT_INCLUDE_DIRS=$inc" "-DKONTE_OT_LIBS=$libs"
  if ($LASTEXITCODE -ne 0) { throw "CMake 配置失败" }
  cmake --build $build --config Release
  if ($LASTEXITCODE -ne 0) { throw "CMake 构建失败" }
  Write-Host "完成（含 OpenToonz 场景写入）" -ForegroundColor Green
}
