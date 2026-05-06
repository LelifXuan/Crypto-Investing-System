param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("install", "dev", "dev-local", "test", "lint", "check", "clean", "release-zip")]
    [string]$Task
)

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
python scripts/tasks.py $Task
exit $LASTEXITCODE
