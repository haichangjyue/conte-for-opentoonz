# SPDX-License-Identifier: BSD-3-Clause
# Konte PoC 一键演示：生成示例项目 → 导出（A4 PDF + 参考图 + ScenePlan + manifest）→ 页面预览
# 用法：pwsh -File scripts/run_demo.ps1 [-BasePsd <路径>] [-Out <目录>]

param(
    [string]$BasePsd = "X:\agent\PhotoshopCT\footage\scfilms_StoryBoard.psd",
    [string]$Out = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$poc  = Join-Path $repo "poc"

# 选 Python：环境变量 KONTE_PY > 随附运行时 > PATH
$py = $env:KONTE_PY
if (-not $py) {
    $cand = "C:\Users\haichangjyue\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $cand) { $py = $cand } else { $py = "python" }
}

Push-Location $poc
try {
    $env:PYTHONPATH = $poc
    Write-Host "[1/3] 生成示例项目 ..." -ForegroundColor Cyan
    & $py tools\make_demo.py | Out-Null

    $outDir = if ($Out) { $Out } else { "examples\EP01\out" }
    Write-Host "[2/3] 导出（A4·5-cut PDF + 参考图 + ScenePlan + manifest） ..." -ForegroundColor Cyan
    $cliArgs = @("-m", "konte_poc", "export", "examples\EP01\konte.json", "--out", $outDir)
    if (Test-Path $BasePsd) { $cliArgs += @("--base-psd", $BasePsd) }
    & $py @cliArgs | Out-Null

    Write-Host "[3/3] 生成页面预览 ..." -ForegroundColor Cyan
    & $py tools\preview_pages.py

    Write-Host "`n完成。产物目录：$outDir" -ForegroundColor Green
    Write-Host "  - storyboard.pdf  (A4·5-cut 分镜)" -ForegroundColor Green
    Write-Host "  - manifest.json   (产物清单)" -ForegroundColor Green
    Write-Host "  - scenes\*.sceneplan.json (→ C++ 内核生成 .tnz)" -ForegroundColor Green
}
finally {
    Pop-Location
}
