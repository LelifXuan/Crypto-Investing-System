#!/usr/bin/env sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

export APP_DISTRIBUTION_MODE=portable
export APP_BUNDLE_ROOT="$SCRIPT_DIR"
export APP_RUNTIME_ROOT="$SCRIPT_DIR/runtime"
export APP_PORT="${APP_PORT:-8000}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
python "$SCRIPT_DIR/scripts/portable_preflight.py" || exit 1
python -m uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT"
