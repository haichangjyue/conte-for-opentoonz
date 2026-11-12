# SPDX-License-Identifier: BSD-3-Clause
# 端到端交付打包：Python（参考图/PDF/manifest/ScenePlan）+ C++ konte-export（.tnz）→ 可交付目录 + zip
param(
  [string]$Project   = "",
  [string]$OutRoot   = "X:\agent\build\deliverables",
  [string]$BasePsd   = "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd",
  [string]$Exporter  = "X:\agent\build\opentoonz\Release\konte-export.exe",
  [string]$Template  = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Project) { $Project = "$repo\poc\examples\EP01\konte.json" }

$py = $env:KONTE_PY
if (-not $py) {
  $cand = "C:\Users\haichangjyue\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $cand) { $py = $cand } else { $py = "python" }
}

# 运行时 DLL 搜索路径（konte-export 需要 Qt/OpenCV/thirdparty）
$tp = "$repo\toonz\thirdparty"
$env:TOONZROOT = "$repo\toonz\stuff"
$env:PATH = @(
  "X:\agent\build\opentoonz\Release",
  "X:\agent\tools\Qt\5.15.2\msvc2019_64\bin",
  "X:\agent\tools\opencv\opencv\build\x64\vc16\bin",
  "$tp\libmypaint\dist\64", "$tp\glew\glew-1.9.0\bin\64bit", "$tp\glut\3.7.6\lib",
  $env:PATH
) -join ';'

Push-Location "$repo\poc"
try {
  $env:PYTHONPATH = (Get-Location).Path
  $cliArgs = @("-m", "konte_poc", "package", $Project, "--out-root", $OutRoot, "--exporter", $Exporter)
  if ($BasePsd -and (Test-Path $BasePsd)) { $cliArgs += @("--base-psd", $BasePsd) }
  if ($Template) { $cliArgs += @("--template", $Template) }
  & $py @cliArgs
  Write-Host ("package exit=" + $LASTEXITCODE)
}
finally { Pop-Location }
