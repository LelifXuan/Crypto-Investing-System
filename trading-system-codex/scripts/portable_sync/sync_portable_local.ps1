param(
  [string]$Destination = "E:\Personal\Research\Crypto Investing System\TradingSystemPortable",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
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

$runtimeRoot = Join-Path $Destination "runtime"
$runtimeConfig = Join-Path $runtimeRoot "config"
$portableEnv = Join-Path $runtimeConfig "portable.env"
New-Item -ItemType Directory -Path $runtimeConfig -Force | Out-Null

$apiEnvNames = @(
  "FRED_API_KEY",
  "BLS_API_KEY",
  "BEA_API_KEY",
  "COINMARKETCAP_API_KEY",
  "ALPHA_VANTAGE_API_KEY",
  "NASDAQ_DATA_LINK_API_KEY",
  "OPENEXCHANGERATES_APP_ID",
  "TUSHARE_TOKEN",
  "ZHITUAPI_TOKEN",
  "AGUSHUJU_API_KEY",
  "AGUSHUJU_API_BASE_URL",
  "TWELVEDATA_API_KEY",
  "TIINGO_API_KEY",
  "MARKET_EVENTS_TRANSLATION_PROVIDER",
  "MARKET_EVENTS_TRANSLATE_ENABLED",
  "MARKET_EVENTS_TRANSLATION_WORKER_ENABLED",
  "PORTABLE_REMOTE_TRANSLATION_ENABLED",
  "TENCENT_TMT_SECRET_ID",
  "TENCENT_TMT_SECRET_KEY",
  "TENCENT_TMT_REGION",
  "TENCENT_TMT_ENDPOINT",
  "TENCENT_TMT_PROJECT_ID"
)

function Read-EnvFileValue {
  param(
    [string]$Path,
    [string]$Name
  )
  if (-not (Test-Path -LiteralPath $Path)) {
    return $null
  }
  $pattern = "^\s*$([regex]::Escape($Name))\s*=\s*(.*?)\s*$"
  foreach ($line in Get-Content -LiteralPath $Path) {
    $match = [regex]::Match($line, $pattern)
    if ($match.Success) {
      return $match.Groups[1].Value.Trim().Trim('"').Trim("'")
    }
  }
  return $null
}

function Upsert-EnvLine {
  param(
    [string[]]$Lines,
    [string]$Name,
    [string]$Value
  )
  $prefix = "$Name="
  $updated = @()
  $found = $false
  foreach ($line in $Lines) {
    if ($line.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
      if (-not $found) {
        $updated += "$Name=$Value"
        $found = $true
      }
    } else {
      $updated += $line
    }
  }
  if (-not $found) {
    $updated += "$Name=$Value"
  }
  return $updated
}

$sourceEnv = Join-Path $ProjectRoot ".env"
$localSecretEnv = Join-Path $ProjectRoot ".local_secrets\portable_api.env"
$externalSecretEnv = Join-Path (Split-Path -Parent $ProjectRoot) "portable_api.env"
$secretEnvFiles = @($sourceEnv, $localSecretEnv, $externalSecretEnv)
$envLines = @(
  "APP_DISTRIBUTION_MODE=portable",
  "APP_HOST=127.0.0.1",
  "APP_PORT=8000",
  "APP_DEBUG=false",
  "LOCAL_ONLY_ENFORCED=true",
  "ENABLE_DOCS=false",
  "ENABLE_OPENAPI=false",
  "WORKER_PROFILE=desktop_light",
  "MARKET_EVENTS_TRANSLATE_ENABLED=true",
  "MARKET_EVENTS_TRANSLATION_WORKER_ENABLED=true",
  "MARKET_EVENTS_TRANSLATION_PROVIDER=local_glossary",
  "PORTABLE_REMOTE_TRANSLATION_ENABLED=false",
  "JWT_SECRET_KEY=$([guid]::NewGuid().ToString('N'))$([guid]::NewGuid().ToString('N'))",
  "BOOTSTRAP_ADMIN_USERNAME=localadmin",
  "BOOTSTRAP_ADMIN_PASSWORD=$([guid]::NewGuid().ToString('N'))"
)
$embeddedKeyCount = 0
foreach ($name in $apiEnvNames) {
  $value = $null
  foreach ($envFile in $secretEnvFiles) {
    $value = Read-EnvFileValue -Path $envFile -Name $name
    if ($null -ne $value -and $value -ne "") {
      break
    }
  }
  if ($null -ne $value -and $value -ne "") {
    $envLines = Upsert-EnvLine -Lines $envLines -Name $name -Value $value
    $embeddedKeyCount += 1
  }
}
$tencentId = $null
$tencentKey = $null
foreach ($envFile in $secretEnvFiles) {
  if ($null -eq $tencentId -or $tencentId -eq "") {
    $tencentId = Read-EnvFileValue -Path $envFile -Name "TENCENT_TMT_SECRET_ID"
  }
  if ($null -eq $tencentKey -or $tencentKey -eq "") {
    $tencentKey = Read-EnvFileValue -Path $envFile -Name "TENCENT_TMT_SECRET_KEY"
  }
}
if ($null -ne $tencentId -and $tencentId -ne "" -and $null -ne $tencentKey -and $tencentKey -ne "") {
  $envLines = Upsert-EnvLine -Lines $envLines -Name "MARKET_EVENTS_TRANSLATION_PROVIDER" -Value "tencent_tmt"
  $envLines = Upsert-EnvLine -Lines $envLines -Name "PORTABLE_REMOTE_TRANSLATION_ENABLED" -Value "true"
}
$envLines | Set-Content -LiteralPath $portableEnv -Encoding UTF8
Write-Output "Embedded portable API config written: $embeddedKeyCount entries"

$embeddedPython = Join-Path $Destination "runtime_env\python\python.exe"
if (-not (Test-Path -LiteralPath $embeddedPython)) {
  throw "embedded Python is missing after sync: $embeddedPython"
}

$env:APP_DISTRIBUTION_MODE = "portable"
$env:APP_BUNDLE_ROOT = $Destination
$env:APP_RUNTIME_ROOT = $runtimeRoot
& $embeddedPython (Join-Path $Destination "scripts\portable_preflight.py")
if ($LASTEXITCODE -ne 0) {
  throw "portable preflight failed with exit code $LASTEXITCODE"
}

$runtimeGeneratedDirs = @("data", "logs", "cache", "tmp")
foreach ($rel in $runtimeGeneratedDirs) {
  $path = Join-Path $runtimeRoot $rel
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}
$runtimeGeneratedFiles = @("storage_manifest.json")
foreach ($rel in $runtimeGeneratedFiles) {
  $path = Join-Path $runtimeRoot $rel
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Force
  }
}

Write-Output "Portable local directory is ready: $Destination"
