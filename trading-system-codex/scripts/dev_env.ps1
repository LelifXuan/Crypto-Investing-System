param(
  [switch]$StartServer
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..")
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$VenvRoot = Join-Path $WorkspaceRoot "runtime_dev\.venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
  throw "Development venv not found: $PythonExe. Create it with: py -3.11 -m venv `"$VenvRoot`""
}

$env:APP_RUNTIME_ROOT = Join-Path $WorkspaceRoot "runtime_dev\source_runtime"
$env:PYTHONPATH = $ProjectRoot
Set-Location $ProjectRoot

if ($StartServer) {
  & $PythonExe "scripts\tasks.py" "dev-local"
  exit $LASTEXITCODE
}

Write-Output "Project root: $ProjectRoot"
Write-Output "Python: $PythonExe"
Write-Output "Runtime root: $env:APP_RUNTIME_ROOT"
Write-Output "Run source server: .\scripts\dev_env.ps1 -StartServer"
