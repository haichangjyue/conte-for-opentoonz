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
if (-not $repo) { $repo = "X:\agent\NARRATIVISM_otz\repos\konte-for-opentoonz" }
if (-not $Project) { $Project = "$repo\poc\examples\EP01\konte.json" }

$py = $env:KONTE_PY
if (-not $py) {
  $cand = "C:\Users\haichangjyue\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $cand) { $py = $cand } else { $py = "python" }
}

# 运行时 DLL 搜索路径（konte-export 需要 Qt/OpenCV/thirdparty）
$thirdparty = "X:\agent\NARRATIVISM_otz\repos\konte-for-opentoonz\toonz\thirdparty"
$env:TOONZROOT = "X:\agent\NARRATIVISM_otz\repos\konte-for-opentoonz\toonz\stuff"
# 隔离 TOONZ 配置目录：避免导出进程改写用户 OpenToonz 的 preferences.ini（含界面语言）
$otIso = "X:\agent\build\ot_iso"
foreach ($d in 'root','profiles','config','projects','library','studopalette','fxs') {
  New-Item -ItemType Directory -Force -Path ("X:\agent\build\ot_iso\" + $d) | Out-Null
}
$env:TOONZPROFILES     = "X:\agent\build\ot_iso\profiles"
$env:TOONZCONFIG       = "X:\agent\build\ot_iso\config"
$env:TOONZPROJECTS     = "X:\agent\build\ot_iso\projects"
$env:TOONZLIBRARY      = "X:\agent\build\ot_iso\library"
$env:TOONZSTUDIOPALETTE= "X:\agent\build\ot_iso\studopalette"
$env:TOONZFXPRESETS    = "X:\agent\build\ot_iso\fxs"
$env:PATH = @(
  "X:\agent\build\opentoonz\Release",
  "X:\agent\tools\Qt\5.15.2\msvc2019_64\bin",
  "X:\agent\tools\opencv\opencv\build\x64\vc16\bin",
  "X:\agent\NARRATIVISM_otz\repos\konte-for-opentoonz\toonz\thirdparty\libmypaint\dist\64",
  "X:\agent\NARRATIVISM_otz\repos\konte-for-opentoonz\toonz\thirdparty\glew\glew-1.9.0\bin\64bit",
  "X:\agent\NARRATIVISM_otz\repos\konte-for-opentoonz\toonz\thirdparty\glut\3.7.6\lib",
  "C:\Windows\System32", "C:\Windows", "C:\Windows\System32\Wbem",
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
