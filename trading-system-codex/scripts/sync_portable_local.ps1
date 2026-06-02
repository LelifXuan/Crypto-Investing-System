param(
  [string]$Destination = "E:\Personal\Research\Crypto Investing System\TradingSystemPortable",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainScript = Join-Path $ScriptPath "portable_sync\sync_portable_local.ps1"

# Delegates to the main workflow, which runs build_portable_bundle.py and portable_preflight.py.
$env:RELEASE_STRICT = "1"
& $MainScript -Destination $Destination -SkipBuild:$SkipBuild
exit $LASTEXITCODE
