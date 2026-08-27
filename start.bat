@echo off
cd /d "%~dp0"

echo ============================================================
echo   Crypto Research Terminal  V2.2
echo ============================================================

rem --- check code directory ---
if not exist "source\app\main.py" (
    echo [ERROR] source\app\main.py not found, please extract the zip completely.
    pause
    exit /b 1
)
cd /d "%~dp0source"

rem --- prefer embedded python ---
if exist "runtime_python\python.exe" (
    set "PY=%~dp0source\runtime_python\python.exe"
) else (
    echo [WARN] embedded python not found, falling back to system python...
    set "PY=python"
)

rem --- dependency check ---
"%PY%" -c "import sqlalchemy, fastapi, uvicorn" 2>nul
if errorlevel 1 (
    echo [ERROR] dependencies missing, please run:
    echo        "%PY%" -m pip install -e .
    pause
    exit /b 1
)

echo.
echo Starting... open http://127.0.0.1:8002/monitoring-page
echo Press CTRL+C to stop. Close this window to exit.
echo ------------------------------------------------------------
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8002
pause
