param(
  [switch]$StartServer
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..")
# V1.5.x expected a sibling `runtime_dev/.venv`. The project now uses the
# system Python and the in-repo `runtime/` dir for state. APP_RUNTIME_ROOT
# is left unset so app_paths falls back to `<repo>/runtime/` automatically.
$PythonExe = (Get-Command python -ErrorAction Stop).Source
$env:APP_RUNTIME_ROOT = ""
$env:PYTHONPATH = $ProjectRoot
Set-Location $ProjectRoot

if ($StartServer) {
  & $PythonExe "scripts\tasks.py" "dev-local"
  exit $LASTEXITCODE
}

Write-Output "Project root: $ProjectRoot"
Write-Output "Python: $PythonExe"
Write-Output "Runtime root: <repo>/runtime/"
Write-Output "Run source server: .\scripts\dev_env.ps1 -StartServer"
