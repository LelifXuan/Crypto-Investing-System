@echo off
setlocal
cd /d "%~dp0"

set "APP_DISTRIBUTION_MODE=portable"
set "APP_BUNDLE_ROOT=%~dp0"
set "APP_RUNTIME_ROOT=%~dp0runtime"
if not defined APP_PORT set "APP_PORT=8000"
if exist "%~dp0runtime\config\portable.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0runtime\config\portable.env") do (
    if /I "%%A"=="APP_PORT" set "APP_PORT=%%B"
  )
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
set "APP_PYTHON_EXE=%~dp0runtime_env\python\python.exe"
set "APP_LOG_DIR=%~dp0runtime\logs"
set "APP_CONSOLE_LOG=%APP_LOG_DIR%\portable_console.log"

if not exist "%APP_LOG_DIR%" mkdir "%APP_LOG_DIR%" >nul 2>nul

echo Trading System Portable Launcher
echo Bundle root: %~dp0
echo Runtime root: %APP_RUNTIME_ROOT%
echo Embedded Python: %APP_PYTHON_EXE%
echo Port: %APP_PORT%
echo Log: %APP_CONSOLE_LOG%
echo.
>>"%APP_CONSOLE_LOG%" echo ==== start_portable %DATE% %TIME% ====
>>"%APP_CONSOLE_LOG%" echo Bundle root: %~dp0
>>"%APP_CONSOLE_LOG%" echo Runtime root: %APP_RUNTIME_ROOT%
>>"%APP_CONSOLE_LOG%" echo Embedded Python: %APP_PYTHON_EXE%
>>"%APP_CONSOLE_LOG%" echo Port: %APP_PORT%

if not exist "%APP_PYTHON_EXE%" (
  echo error: embedded Python runtime missing: %APP_PYTHON_EXE%
  echo.
  echo This launcher is only for the generated portable bundle.
  echo It requires runtime_env\python inside the same folder.
  echo.
  echo If you are working from the source repository, use:
  echo   start_source.bat
  echo or:
  echo   powershell -ExecutionPolicy Bypass -File .\scripts\dev_env.ps1 -StartServer
  echo.
  echo If you want the portable app, use the generated folder:
  echo   ..\TradingSystemPortable\start_portable.bat
  >>"%APP_CONSOLE_LOG%" echo error: embedded Python runtime missing: %APP_PYTHON_EXE%
  goto fail
)

echo Running preflight...
"%APP_PYTHON_EXE%" "%~dp0scripts\portable_preflight.py" >>"%APP_CONSOLE_LOG%" 2>&1
if errorlevel 1 (
  echo preflight failed. See log: %APP_CONSOLE_LOG%
  type "%APP_CONSOLE_LOG%"
  goto fail
)

echo Starting local server at http://127.0.0.1:%APP_PORT%
echo Keep this window open while using the app.
echo.
"%APP_PYTHON_EXE%" "%~dp0scripts\portable_server.py" >>"%APP_CONSOLE_LOG%" 2>&1
echo server exited. See log: %APP_CONSOLE_LOG%
type "%APP_CONSOLE_LOG%"
goto fail

:fail
echo.
echo Startup failed or the server exited. Press any key to close this window.
pause >nul
exit /b 1
