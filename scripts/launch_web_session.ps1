# SPDX-License-Identifier: BSD-3-Clause
# 一键启动 NARRATIVISM Web 会话（Bridge + Web 编辑器），供 OT 侧 / 桌面快捷方式调用。
# 例：pwsh -File scripts\launch_web_session.ps1 -Project poc\examples\EP01\konte.json
param(
  [Parameter(Mandatory = $true)][string]$Project,
  [string]$WebRoot,
  [string]$BindHost = "127.0.0.1",
  [string]$PublicHost,
  [int]$BridgePort = 17890,
  [int]$WebPort = 5173,
  [string]$Pin,
  [string]$BasePsd,
  [switch]$NoOpen,
  [string]$SessionFile,
  [switch]$Json
)
$ErrorActionPreference = "Stop"

$py = $env:KONTE_PY
if (-not $py) {
  $cand = "C:\Users\haichangjyue\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $cand) { $py = $cand } else { $py = "python" }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $repoRoot "poc\tools\launch_web_session.py"
if (-not (Test-Path $tool)) { throw "找不到启动器: $tool" }

$argv = @($tool, "--project", $Project, "--host", $BindHost, "--bridge-port", "$BridgePort", "--web-port", "$WebPort")
if ($PublicHost)  { $argv += @("--public-host", $PublicHost) }
if ($WebRoot)     { $argv += @("--web-root", $WebRoot) }
if ($Pin)         { $argv += @("--pin", $Pin) }
if ($BasePsd)     { $argv += @("--base-psd", $BasePsd) }
if ($SessionFile) { $argv += @("--session-file", $SessionFile) }
if ($NoOpen)      { $argv += "--no-open" }
if ($Json)        { $argv += "--json" }

& $py @argv
exit $LASTEXITCODE
