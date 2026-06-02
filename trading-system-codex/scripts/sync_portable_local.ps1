param(
  [string]$Destination = "E:\Personal\Research\Crypto Investing System\TradingSystemPortable",
  [switch]$SkipBuild,
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$PortableRoot = Join-Path $ProjectRoot "dist\portable_bundle"
$Python = "python"

function Write-Log {
  param([string]$Message)
  Write-Output $Message
}

if ($WhatIf) {
  Write-Log "WHATIF: portable sync would target $Destination"
  Write-Log "WHATIF: portable build would run via $Python"
  exit 0
}

# Concurrency guard: refuse to sync if a previous sync lock is still
# held by a running process. Lock is removed automatically on exit
# via the trailing Remove-Item.
$lockPath = Join-Path $PortableRoot ".sync.lock"
if (Test-Path -LiteralPath $lockPath) {
  $holderPid = $null
  try {
    $holder = Get-Content -LiteralPath $lockPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    $holderPid = $holder.pid
  } catch {}
  if ($holderPid -and (Get-Process -Id $holderPid -ErrorAction SilentlyContinue)) {
    throw "another portable sync is running (pid $holderPid); lock at $lockPath"
  }
  Write-Log "stale sync lock found (pid $holderPid no longer alive); removing"
  Remove-Item -LiteralPath $lockPath -Force
}

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

# Take the sync lock once the build is known-good. We write the
# lock AFTER the build step (rather than before) so a failed build
# does not leave a stale lock blocking subsequent runs.
$lockPath = Join-Path $PortableRoot ".sync.lock"
$portableRootReady = (Test-Path -LiteralPath $PortableRoot)
if ($portableRootReady -and -not (Test-Path -LiteralPath $lockPath)) {
  $lockPath | Set-Content -Value (ConvertTo-Json @{ pid = $PID; started_at = (Get-Date).ToString('o') }) -Encoding UTF8
  $script:SyncLockPath = $lockPath
  $script:CleanupLock = {
    param($p)
    if ($p -and (Test-Path -LiteralPath $p)) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
  }
  # Register cleanup so the lock is removed even if the script
  # exits via an unhandled exception.
  Register-EngineEvent -SourceIdentifier ([System.Guid]::NewGuid().ToString()) -Action {
    if ($script:CleanupLock) { & $script:CleanupLock $script:SyncLockPath }
  } | Out-Null
  $syncLockRegistered = $true
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

# Refresh portable_excludes.json so downstream tooling agrees on what is
# forbidden. release_common.dump_portable_excludes is the single source of
# truth consumed by verify_portable_release.py and this script.
$pythonDeps = & $Python -c "import sys; sys.path.insert(0, r'$($ProjectRoot.Path)'); sys.path.insert(0, r'$($ProjectRoot.Path)\scripts'); from release_common import dump_portable_excludes, PORTABLE_EXCLUDES_JSON; print(PORTABLE_EXCLUDES_JSON); dump_portable_excludes()" 2>$null
$excludesJsonPath = $pythonDeps | Select-Object -Last 1
if ($null -ne $excludesJsonPath -and $excludesJsonPath -ne "" -and (Test-Path -LiteralPath $excludesJsonPath)) {
  $excludes = Get-Content -LiteralPath $excludesJsonPath -Raw | ConvertFrom-Json
} else {
  throw "Failed to refresh portable_excludes.json from release_common"
}

# Apply forbidden-artifact cleanup using the JSON-loaded rules
foreach ($name in $excludes.excluded_dirs) {
  $path = Join-Path $Destination $name
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}
Get-ChildItem -LiteralPath $Destination -Recurse -Force -Directory -Filter "__pycache__" |
  Sort-Object FullName -Descending |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
foreach ($name in $excludes.excluded_files) {
  Get-ChildItem -LiteralPath $Destination -Recurse -Force -File -Filter $name |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}
foreach ($suffix in $excludes.excluded_suffixes) {
  Get-ChildItem -LiteralPath $Destination -Recurse -Force -File -Filter "*$suffix" |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}

$runtimeRoot = Join-Path $Destination "runtime"
$runtimeConfig = Join-Path $runtimeRoot "config"
$portableEnv = Join-Path $runtimeConfig "portable.env"
New-Item -ItemType Directory -Path $runtimeConfig -Force | Out-Null

# Build the list of secret keys to embed by parsing portable.env.example.
# This keeps the sync script in lock-step with the example file: adding a
# new key in portable.env.example automatically flows into the embedded
# portable.env without editing this script.
$envExamplePath = Join-Path $ProjectRoot "portable.env.example"
$apiEnvNames = New-Object System.Collections.Generic.List[string]
if (Test-Path -LiteralPath $envExamplePath) {
  $keyPattern = '^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*='
  foreach ($line in Get-Content -LiteralPath $envExamplePath) {
    $trimmed = $line.TrimStart()
    if ($trimmed.StartsWith('#') -or $trimmed -eq '') { continue }
    if ($match = [regex]::Match($trimmed, $keyPattern)) {
      $name = $match.Groups[1].Value
      # Heuristic: portable secrets use API_KEY / TOKEN / SECRET / PASSWORD
      # or are explicitly upper-snake. Skip plain DOC/EXPLAINATION lines.
      if ($name -match '(API_KEY|TOKEN|SECRET|PASSWORD)$' -or $name -match '^TENCENT_') {
        $apiEnvNames.Add($name) | Out-Null
      }
    }
  }
}
$apiEnvNames = $apiEnvNames | Select-Object -Unique

function Read-EnvFileValue {
  param(
    [string]$Path,
    [string]$Name
  )
  if (-not (Test-Path -LiteralPath $Path)) {
    return $null
  }
  $pattern = "^\s*(?:export\s+)?$([regex]::Escape($Name))\s*=\s*(.*?)\s*$"
  foreach ($line in Get-Content -LiteralPath $Path) {
    $trimmed = $line.TrimStart()
    if ($trimmed.StartsWith('#')) { continue }
    $match = [regex]::Match($line, $pattern)
    if ($match.Success) {
      $value = $match.Groups[1].Value.Trim()
      # Strip inline comments ("# foo" at end of line)
      $hashIdx = $value.IndexOf('#')
      if ($hashIdx -ge 0) {
        $value = $value.Substring(0, $hashIdx).Trim()
      }
      $value = $value.Trim('"').Trim("'")
      if ($value -eq "") { return $null }
      return $value
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

function Set-ProviderIfKeysPresent {
  param(
    [string[]]$RequiredKeys,
    [string]$ProviderName,
    [string]$ProviderEnvVar,
    [hashtable]$Secrets,
    [ref]$EnvLines,
    [string]$RemoteVar = $null,
    [string]$RemoteValue = $null
  )
  foreach ($key in $RequiredKeys) {
    $value = $Secrets[$key]
    if ($null -eq $value -or $value -eq "") { return }
  }
  $EnvLines.Value = Upsert-EnvLine -Lines $EnvLines.Value -Name $ProviderEnvVar -Value $ProviderName
  if ($null -ne $RemoteVar -and $null -ne $RemoteValue) {
    $EnvLines.Value = Upsert-EnvLine -Lines $EnvLines.Value -Name $RemoteVar -Value $RemoteValue
  }
}

$sourceEnv = Join-Path $ProjectRoot ".env"
$localSecretEnv = Join-Path $ProjectRoot ".local_secrets\portable_api.env"
$externalSecretEnv = Join-Path (Split-Path -Parent $ProjectRoot) "portable_api.env"
$secretEnvFiles = @($sourceEnv, $localSecretEnv, $externalSecretEnv)

# Load all secrets once into a hashtable instead of 3 file reads per key.
$secrets = @{}
foreach ($envFile in $secretEnvFiles) {
  if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
      $trimmed = $line.TrimStart()
      if ($trimmed.StartsWith('#') -or $trimmed -eq '') { continue }
      if ($match = [regex]::Match($trimmed, '^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$')) {
        $name = $match.Groups[1].Value
        $value = $match.Groups[2].Value.Trim()
        $hashIdx = $value.IndexOf('#')
        if ($hashIdx -ge 0) { $value = $value.Substring(0, $hashIdx).Trim() }
        $value = $value.Trim('"').Trim("'")
        if ($value -ne "" -and -not $secrets.ContainsKey($name)) {
          $secrets[$name] = $value
        }
      }
    }
  }
}

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
  if ($secrets.ContainsKey($name)) {
    $value = $secrets[$name]
    if ($null -ne $value -and $value -ne "") {
      $envLines = Upsert-EnvLine -Lines $envLines -Name $name -Value $value
      $embeddedKeyCount += 1
    }
  }
}

# Tencent TMT: only enable if both id and key are present.
Set-ProviderIfKeysPresent `
  -RequiredKeys @("TENCENT_TMT_SECRET_ID", "TENCENT_TMT_SECRET_KEY") `
  -ProviderName "tencent_tmt" `
  -ProviderEnvVar "MARKET_EVENTS_TRANSLATION_PROVIDER" `
  -Secrets $secrets `
  -EnvLines ([ref]$envLines) `
  -RemoteVar "PORTABLE_REMOTE_TRANSLATION_ENABLED" `
  -RemoteValue "true"

# Write portable.env with UTF-8 without BOM. PowerShell's
# Set-Content -Encoding UTF8 emits a BOM, which some Windows Python
# versions do not handle gracefully when reading .env files.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($portableEnv, $envLines, $utf8NoBom)
Write-Log "Embedded portable API config written: $embeddedKeyCount entries"

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

foreach ($rel in $excludes.residue_dirs) {
  $path = Join-Path $runtimeRoot $rel
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}
foreach ($rel in $excludes.residue_files) {
  $path = Join-Path $runtimeRoot $rel
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Force
  }
}

Write-Log "Portable local directory is ready: $Destination"
