# Trading System FastAPI

Windows-first local crypto research and trading management app built with `FastAPI + SQLite + Gate.io`.

## V1.5 Highlights

V1.5 focuses on the **monitoring overview explainability loop**. The terminal
summary is now produced as a three-row `decision_brief`:

- `市场情况` (market situation)
- `交易指引` (trading guidance)
- `风险点 / 失效条件` (risk / invalidation)

Each row carries an `evidence_strength` (0-1) computed from the new
multi-period conflict matrix in `terminal_summary.decision_brief.source_alignment.matrix`.
When evidence drops below `0.5` the row tone is demoted to `warning`
and the summary is prefixed with an explicit uncertainty note.

The decision_brief is persisted to `ComputedDatasetCache` after every
`MonitoringDashboardService.refresh_bundle` so users can review
historical decisions through `GET /monitoring/decision-brief/history`.

See `docs/CHANGELOG.md` for the full V1.5 change set and
`docs/RELEASE.md` for the V1.5 pre-release checklist.

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

Local runtime state is intentionally kept outside this repository:

- `..\runtime_dev\.venv`: development Python environment
- `..\runtime_dev\source_runtime`: source-mode database, logs, cache, and temp files
- `..\TradingSystemPortable`: generated portable build; do not edit it by hand

## Windows Quick Start

1. Create and activate a supported virtual environment outside the source tree.

```powershell
py -3.11 -m venv ..\runtime_dev\.venv
..\runtime_dev\.venv\Scripts\Activate.ps1
```

You can also use:

```powershell
py -3.14 -m venv ..\runtime_dev\.venv
```

2. Copy the example environment file.

```powershell
Copy-Item .env.example .env
```

3. Install dependencies and run the quality check.

```powershell
python scripts/tasks.py install
python scripts/tasks.py check
```

4. Start the local app.

```powershell
python scripts/tasks.py dev-local
```

If you use the workspace-standard external environment, this helper starts the
source instance on port `8002` and keeps runtime files out of the repository:

```powershell
.\scripts\dev_env.ps1 -StartServer
```

For double-click startup from the source tree, use:

```powershell
.\start_source.bat
```

`start_portable.bat` is only for the generated `TradingSystemPortable` bundle.
It expects an embedded Python runtime at `runtime_env\python` and will fail when
double-clicked from the source repository.

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
- `check`: run lint, tests, compile smoke, import check, and JS syntax check
- `clean`: remove generated caches, logs, and safe local runtime artifacts
- `release-zip`: build the GitHub release zip
- `build-portable`: build the portable distribution bundle
- `portable-preflight`: validate the portable bundle before release

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
