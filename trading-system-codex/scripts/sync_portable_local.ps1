param(
  [string]$Destination = "E:\Personal\Research\Crypto Investing System\TradingSystemPortable",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainScript = Join-Path $ScriptPath "portable_sync\sync_portable_local.ps1"

& $MainScript -Destination $Destination -SkipBuild:$SkipBuild
exit $LASTEXITCODE
