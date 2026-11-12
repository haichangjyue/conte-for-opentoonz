# SPDX-License-Identifier: BSD-3-Clause
# 构建 konte-bridge-qt（Qt5 Core/Network，MSVC cl，无需 moc）。
# 用法：pwsh -File scripts/build_bridge_qt.ps1 [-QtDir ...] [-OutDir ...]
param(
  [string]$QtDir = "X:\agent\tools\Qt\5.15.2\msvc2019_64",
  [string]$OutDir = "",
  [string]$VcVars = "X:\agent\tools\vsbuild\VC\Auxiliary\Build\vcvars64.bat"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $repo "build\bridge-qt" }
$srcDir = Join-Path $repo "bridge-qt\src"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$qtInc = Join-Path $QtDir "include"
$qtLib = Join-Path $QtDir "lib"
$qtBin = Join-Path $QtDir "bin"
foreach ($p in @($qtInc, $qtLib, $VcVars)) { if (-not (Test-Path $p)) { throw "缺少: $p" } }

$cl = @"
call "$VcVars" >nul 2>&1
cl /nologo /utf-8 /std:c++17 /EHsc /MD /O2 /DNOMINMAX /DUNICODE /D_UNICODE ^
 /I"$qtInc" /I"$qtInc\QtCore" /I"$qtInc\QtNetwork" /I"$qtInc\QtGui" ^
 "$srcDir\main.cpp" ^
 /Fe:"$OutDir\konte-bridge-qt.exe" ^
 /link /LIBPATH:"$qtLib" Qt5Core.lib Qt5Network.lib Qt5Gui.lib ws2_32.lib
"@
$bat = Join-Path $OutDir "_build.bat"
Set-Content -Path $bat -Value $cl -Encoding ASCII
cmd /c "`"$bat`""
if ($LASTEXITCODE -ne 0) { throw "cl 编译失败（exit $LASTEXITCODE）" }
Remove-Item $bat -Force

# 复制 Qt 运行时 DLL，便于独立运行
foreach ($dll in @("Qt5Core.dll", "Qt5Network.dll", "Qt5Gui.dll")) {
  $s = Join-Path $qtBin $dll
  if (Test-Path $s) { Copy-Item $s $OutDir -Force }
}
Write-Host "完成: $OutDir\konte-bridge-qt.exe" -ForegroundColor Green
