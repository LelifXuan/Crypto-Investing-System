# Trading System FastAPI

Windows-first local crypto research and trading management app built with `FastAPI + SQLite + Gate.io`.

## Source Of Truth

- Main project directory: this repository root
- Recommended runtime: local single-user mode
- Supported Python: `3.11` and `3.14`
- Recommended local host: `127.0.0.1`

This project is a local research tool, not a public SaaS app and not an automated execution engine.

## Project Layout

- `app/`: API, workers, services, templates, static assets
- `tests/`: regression and behavior checks
- `alembic/`: database migrations
- `scripts/`: workspace automation, cleanup, release packaging
- `docs/`: project documentation and archived notes

## Windows Quick Start

1. Create and activate a supported virtual environment.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

You can also use:

```powershell
py -3.14 -m venv .venv
```

2. Copy the example environment file.

```powershell
Copy-Item .env.example .env
```

3. Install dependencies.

```powershell
python scripts/tasks.py install
```

4. Start the local app.

```powershell
python scripts/tasks.py dev-local
```

5. Open the local UI.

- Dashboard: [http://127.0.0.1:8002/dashboard](http://127.0.0.1:8002/dashboard)
- Indicators: [http://127.0.0.1:8002/indicators-page](http://127.0.0.1:8002/indicators-page)
- Market events: [http://127.0.0.1:8002/market-events-page](http://127.0.0.1:8002/market-events-page)
- Imports: [http://127.0.0.1:8002/imports-page](http://127.0.0.1:8002/imports-page)

## Windows Task Runner

Use either `python scripts/tasks.py <task>` or `.\scripts\dev.ps1 <task>`.

Available tasks:

- `install`: install editable app and development dependencies
- `dev`: run Uvicorn on `127.0.0.1:8000`
- `dev-local`: run Uvicorn on `127.0.0.1:8002`
- `test`: run `pytest -q`
- `lint`: run `ruff check .`
- `check`: run lint, tests, compile smoke, and `import app.main`
- `clean`: remove generated caches, logs, and safe local runtime artifacts
- `release-zip`: build the GitHub release zip

Development tasks fail fast when:

- Python is not `3.11`
- Python is not `3.11` or `3.14`
- no virtual environment is active
- required tools such as `pytest`, `ruff`, or `uvicorn` are missing

## Makefile Mapping

The `Makefile` remains available for CI and Unix-like environments.

- `make install`
- `make dev`
- `make dev-local`
- `make test`
- `make lint`
- `make check`
- `make clean`
- `make release-zip`

## Health And Stability

- Health endpoints:
  - `/health`
  - `/health/live`
  - `/health/ready`
- Default worker profile: `desktop_light`
- Market event translation uses provider cooldown handling to reduce repeated `429` noise
- Websocket disconnects are treated as recoverable and reconnect automatically

## Cleanup Rules

`python scripts/tasks.py clean` removes only safe generated artifacts:

- `__pycache__`
- `.pytest_cache`
- `.ruff_cache`
- `.mypy_cache`
- `run/`
- `*.pyc`
- `*.log`
- `dist/`
- `build/`
- `site/`
- `htmlcov/`
- `trading_system.db-shm`
- `trading_system.db-wal`
- `trading_system.db-journal`

The cleanup task does not remove:

- `.env`
- `trading_system.db`
- local imported data
- `docs/`
- tests, migrations, or application source files

## Release Packaging

Build the release archive with:

```powershell
python scripts/tasks.py release-zip
```

Output:

```text
dist/trading-system-fastapi-github.zip
```
