param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("install", "dev", "dev-local", "test", "lint", "check", "clean", "release-zip")]
    [string]$Task
)

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
# V1.5.x used a sibling `runtime_dev/.venv` location for the dev venv. The
# project now runs against the system Python with deps installed into the
# active interpreter, so this launcher simply delegates to whatever
# `python` resolves to on PATH.
python scripts/tasks.py $Task
exit $LASTEXITCODE
