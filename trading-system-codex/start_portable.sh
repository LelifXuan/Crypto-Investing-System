#!/usr/bin/env sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

export APP_DISTRIBUTION_MODE=portable
export APP_BUNDLE_ROOT="$SCRIPT_DIR"
export APP_RUNTIME_ROOT="$SCRIPT_DIR/runtime"
export APP_PORT="${APP_PORT:-8000}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
APP_PYTHON_EXE="$SCRIPT_DIR/runtime_env/python/python"
if [ ! -x "$APP_PYTHON_EXE" ]; then
  echo "error: embedded Python runtime missing: $APP_PYTHON_EXE" >&2
  echo "The first true portable release is Windows win-x64. Use start_portable.bat on Windows." >&2
  exit 1
fi
export APP_PYTHON_EXE
"$APP_PYTHON_EXE" "$SCRIPT_DIR/scripts/portable_preflight.py" || exit 1
"$APP_PYTHON_EXE" -m uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT"
