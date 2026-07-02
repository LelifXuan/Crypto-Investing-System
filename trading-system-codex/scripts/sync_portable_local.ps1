param(
  [string]$Destination = "E:\Personal\Research\Crypto Investing System\TradingSystemPortable",
  [switch]$SkipBuild,
  [switch]$SkipBrowserAudit,
  [switch]$ResetRuntime,
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..")
$PortableRoot = Join-Path $ProjectRoot "dist\portable_bundle"
$ReportRoot = Join-Path $ProjectRoot "reports"
$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }

if ($WhatIf) {
  Write-Output "WHATIF build=$(-not $SkipBuild)"
  Write-Output "WHATIF source=$PortableRoot"
  Write-Output "WHATIF destination=$Destination"
  Write-Output "WHATIF preserve=runtime/config,runtime/data,user_exports,imports"
  Write-Output "WHATIF clear=runtime/cache,runtime/tmp"
  Write-Output "WHATIF browser_audit=$(-not $SkipBrowserAudit)"
  exit 0
}

$resolvedDestination = [System.IO.Path]::GetFullPath($Destination)
$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.CommandLine -and
    $_.CommandLine.IndexOf($resolvedDestination, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
  }
if ($running) {
  $ids = ($running | Select-Object -ExpandProperty ProcessId) -join ","
  throw "Portable instance is running from destination (pid=$ids). Stop it before sync."
}

New-Item -ItemType Directory -Path $ReportRoot -Force | Out-Null

if (-not $SkipBuild) {
  $env:RELEASE_STRICT = "1"
  Remove-Item Env:PORTABLE_RUNTIME_STUB -ErrorAction SilentlyContinue
  & $Python (Join-Path $ProjectRoot "scripts\build_portable_bundle.py")
  if ($LASTEXITCODE -ne 0) {
    throw "Portable bundle build failed with exit code $LASTEXITCODE"
  }
}

if (-not (Test-Path -LiteralPath $PortableRoot)) {
  throw "Portable bundle does not exist: $PortableRoot"
}

$syncArgs = @(
  (Join-Path $ProjectRoot "scripts\portable_sync.py"),
  "--bundle", $PortableRoot,
  "--destination", $resolvedDestination,
  "--report", (Join-Path $ReportRoot "portable_sync_v16.json"),
  "--keep-backup"
)
if ($ResetRuntime) {
  $syncArgs += "--reset-runtime"
}
& $Python @syncArgs
if ($LASTEXITCODE -ne 0) {
  throw "Portable staging sync failed with exit code $LASTEXITCODE"
}

try {
  $embeddedPython = Join-Path $resolvedDestination "runtime_env\python\python.exe"
  if (-not (Test-Path -LiteralPath $embeddedPython)) {
    throw "Embedded Python missing after sync: $embeddedPython"
  }
  $env:APP_DISTRIBUTION_MODE = "portable"
  $env:APP_BUNDLE_ROOT = $resolvedDestination
  $env:APP_RUNTIME_ROOT = Join-Path $resolvedDestination "runtime"
  $env:APP_PYTHON_EXE = $embeddedPython
  & $embeddedPython (Join-Path $resolvedDestination "scripts\portable_preflight.py")
  if ($LASTEXITCODE -ne 0) {
    throw "Portable preflight failed with exit code $LASTEXITCODE"
  }

  if (-not $SkipBrowserAudit) {
    & $Python `
      (Join-Path $ProjectRoot "scripts\portable_playwright_audit.py") `
      --portable-root $resolvedDestination `
      --report (Join-Path $ReportRoot "portable_playwright_v16.json") `
      --screenshots (Join-Path $ReportRoot "portable_playwright_screenshots")
    if ($LASTEXITCODE -ne 0) {
      throw "Portable Playwright audit failed with exit code $LASTEXITCODE"
    }
  }

  & $Python (Join-Path $ProjectRoot "scripts\portable_sync.py") `
    --bundle $PortableRoot `
    --destination $resolvedDestination `
    --finalize
} catch {
  & $Python (Join-Path $ProjectRoot "scripts\portable_sync.py") `
    --bundle $PortableRoot `
    --destination $resolvedDestination `
    --rollback
  throw
}

Write-Output "Portable V1.6 sync complete: $resolvedDestination"
