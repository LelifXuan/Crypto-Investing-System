@echo off
setlocal
cd /d "%~dp0"

set "APP_DISTRIBUTION_MODE=portable"
set "APP_BUNDLE_ROOT=%~dp0"
set "APP_RUNTIME_ROOT=%~dp0runtime"
if not defined APP_PORT set "APP_PORT=8000"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo error: python not found on PATH
  exit /b 1
)

python "%~dp0scripts\portable_preflight.py" || exit /b 1
python -m uvicorn app.main:app --host 127.0.0.1 --port %APP_PORT%
