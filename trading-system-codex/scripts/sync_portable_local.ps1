param(
  [string]$Destination = "E:\Personal\Research\Crypto Investing System\TradingSystemPortable",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..")
$PortableRoot = Join-Path $ProjectRoot "dist\portable_bundle"
$Python = "python"

if (-not $SkipBuild) {
  $env:RELEASE_STRICT = "1"
  if ($env:PORTABLE_RUNTIME_STUB -eq "1") {
    throw "PORTABLE_RUNTIME_STUB=1 is not allowed for local portable sync."
  }
  & $Python (Join-Path $ProjectRoot "scripts\build_portable_bundle.py")
  if ($LASTEXITCODE -ne 0) {
    throw "portable bundle build failed with exit code $LASTEXITCODE"
  }
}

if (-not (Test-Path -LiteralPath $PortableRoot)) {
  throw "portable bundle does not exist: $PortableRoot"
}

$DestinationParent = Split-Path -Parent $Destination
if (-not (Test-Path -LiteralPath $DestinationParent)) {
  New-Item -ItemType Directory -Path $DestinationParent | Out-Null
}

if (Test-Path -LiteralPath $Destination) {
  $resolvedDestination = Resolve-Path -LiteralPath $Destination
  $resolvedParent = Resolve-Path -LiteralPath $DestinationParent
  if (-not $resolvedDestination.Path.StartsWith(
      $resolvedParent.Path,
      [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw "Refusing to remove unexpected destination: $resolvedDestination"
  }
  Remove-Item -LiteralPath $resolvedDestination.Path -Recurse -Force
}

New-Item -ItemType Directory -Path $Destination | Out-Null
Get-ChildItem -LiteralPath $PortableRoot -Force | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
}

$cleanupDirs = @(
  "runtime",
  ".pytest_cache",
  ".ruff_cache",
  "logs",
  "tmp",
  "cache"
)
foreach ($rel in $cleanupDirs) {
  $path = Join-Path $Destination $rel
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}

Get-ChildItem -LiteralPath $Destination -Recurse -Force -Directory -Filter "__pycache__" |
  Sort-Object FullName -Descending |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

$forbiddenFiles = @(
  ".env",
  "storage_manifest.json",
  "trading_system.db",
  "trading_system.db-wal",
  "trading_system.db-shm",
  "trading_system.db-journal"
)
foreach ($name in $forbiddenFiles) {
  Get-ChildItem -LiteralPath $Destination -Recurse -Force -File -Filter $name |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}

$embeddedPython = Join-Path $Destination "runtime_env\python\python.exe"
if (-not (Test-Path -LiteralPath $embeddedPython)) {
  throw "embedded Python is missing after sync: $embeddedPython"
}

$env:APP_DISTRIBUTION_MODE = "portable"
$env:APP_BUNDLE_ROOT = $Destination
$env:APP_RUNTIME_ROOT = Join-Path $Destination "runtime"
& $embeddedPython (Join-Path $Destination "scripts\portable_preflight.py")
if ($LASTEXITCODE -ne 0) {
  throw "portable preflight failed with exit code $LASTEXITCODE"
}

$runtime = Join-Path $Destination "runtime"
if (Test-Path -LiteralPath $runtime) {
  Remove-Item -LiteralPath $runtime -Recurse -Force
}

Write-Output "Portable local directory is ready: $Destination"
