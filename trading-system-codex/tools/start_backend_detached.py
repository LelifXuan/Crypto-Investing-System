"""Run uvicorn in the background on port 8002, write logs to runtime/tmp."""
import subprocess
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "runtime" / "tmp"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "uvicorn_8002.log"

with LOG_FILE.open("w", encoding="utf-8") as logf:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8002", "--no-access-log"],
        stdout=logf,
        stderr=subprocess.STDOUT,
        creationflags=0x00000008,  # DETACHED_PROCESS on Windows
    )
    print(f"uvicorn pid={proc.pid} log={LOG_FILE}")
