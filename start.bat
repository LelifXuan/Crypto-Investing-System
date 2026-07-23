@echo off
echo Trading System starting on http://127.0.0.1:8002 ...
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
pause
