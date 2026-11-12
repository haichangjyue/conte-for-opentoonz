# SPDX-License-Identifier: BSD-3-Clause
# OT 侧自动拉起：监听项目目录，新 konte.json 出现即启动 Web 会话。
# 例：pwsh -File scripts\start_ot_watch.ps1 -Root X:\projects\EP01
param(
  [Parameter(Mandatory = $true)][string]$Root,
  [string]$Pattern = "konte.json",
  [double]$Interval = 2,
  [switch]$LaunchExisting,
  [switch]$NoOpen,
  [switch]$DryRun,
  [switch]$Once
)
$ErrorActionPreference = "Stop"
$py = $env:KONTE_PY
if (-not $py) {
  $cand = "C:\Users\haichangjyue\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $cand) { $py = $cand } else { $py = "python" }
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $repoRoot "poc\tools\watch_ot_projects.py"
$argv = @($tool, "--root", $Root, "--pattern", $Pattern, "--interval", "$Interval")
if ($LaunchExisting) { $argv += "--launch-existing" }
if ($NoOpen)         { $argv += "--no-open" }
if ($DryRun)         { $argv += "--dry-run" }
if ($Once)           { $argv += "--once" }
& $py @argv
exit $LASTEXITCODE
