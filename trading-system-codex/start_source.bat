@echo off
setlocal
cd /d "%~dp0"

set "WORKSPACE_ROOT=%~dp0.."
set "DEV_PYTHON=%WORKSPACE_ROOT%\runtime_dev\.venv\Scripts\python.exe"
set "APP_RUNTIME_ROOT=%WORKSPACE_ROOT%\runtime_dev\source_runtime"
set "APP_DISTRIBUTION_MODE=source"
set "APP_BUNDLE_ROOT=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

echo Trading System Source Launcher
echo Source root: %~dp0
echo Runtime root: %APP_RUNTIME_ROOT%
echo Python: %DEV_PYTHON%
echo Port: 8002
echo.

if not exist "%DEV_PYTHON%" (
  echo error: source development Python environment is missing.
  echo Expected: %DEV_PYTHON%
  echo.
  echo Create it from PowerShell:
  echo   py -3.11 -m venv "%WORKSPACE_ROOT%\runtime_dev\.venv"
  echo   "%WORKSPACE_ROOT%\runtime_dev\.venv\Scripts\python.exe" -m pip install -U pip
  echo   "%WORKSPACE_ROOT%\runtime_dev\.venv\Scripts\python.exe" scripts\tasks.py install
  echo.
  echo Press any key to close this window.
  pause >nul
  exit /b 1
)

echo Starting source server at http://127.0.0.1:8002
echo Keep this window open while using the app.
echo.
"%DEV_PYTHON%" scripts\tasks.py dev-local
set "SERVER_EXIT=%ERRORLEVEL%"
echo.
echo Source server exited. Press any key to close this window.
pause >nul
exit /b %SERVER_EXIT%
