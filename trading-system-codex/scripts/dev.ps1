param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("install", "dev", "dev-local", "test", "lint", "check", "clean", "release-zip")]
    [string]$Task
)

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$externalPython = Join-Path $workspaceRoot "runtime_dev\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $externalPython) {
    & $externalPython scripts/tasks.py $Task
} else {
    python scripts/tasks.py $Task
}
exit $LASTEXITCODE
