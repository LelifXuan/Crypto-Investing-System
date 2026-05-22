# Trading System Windows Portable

This is a Windows `win-x64` portable package. It includes Python 3.11 embeddable runtime and
the pinned application dependencies, so users do not need to install Python.

Portable users do not need to set `HTTPS_PROXY` or fill in API keys before opening the
application. The app auto-detects common local proxies, then falls back through live data,
runtime cache, bundled seed cache, web snapshots, and explicit unscored placeholders. Optional
API keys only improve freshness and coverage; missing keys lower confidence instead of making
pages blank.

## Start

If you already have the folder `TradingSystemPortable`, use it directly:

1. Double-click `start_portable.bat`.
2. Open the local URL printed by the console, usually `http://127.0.0.1:8000`.

If you distribute it as an archive later, extract the archive once to a normal writable folder,
for example `TradingSystemPortable`, then use the same `start_portable.bat` entry.

The first start creates `runtime/`:

- `runtime/config/portable.env`
- `runtime/data/trading_system.db`
- `runtime/logs/`
- `runtime/cache/`
- `runtime/tmp/`

`runtime/` is user data. It can be backed up or deleted to rebuild local state. The embedded
runtime lives in `runtime_env/` and should be treated as read-only.

## Change Port

Edit `runtime/config/portable.env` after the first start:

```env
APP_PORT=8002
```

Then restart `start_portable.bat`.

## Disable Background Workers

For offline troubleshooting or low-resource machines:

```env
WORKER_PROFILE=none
```

Accepted disabled values are `none`, `off`, and `disabled`. Pages still show cached snapshots
and degraded states, but background precompute and sync workers will not start.

## Common Errors

- `embedded Python runtime missing`: use the real `win-x64` portable folder. The source archive does
  not contain `runtime_env/python/python.exe`.
- `port already in use`: change `APP_PORT` in `runtime/config/portable.env`.
- `dependency import failed`: rebuild the portable package with `scripts/build_portable_bundle.py`
  or download a fresh release.
- `database locked`: close other running copies, then restart. If needed, back up and remove
  `runtime/data/trading_system.db`.

## Release Integrity

Maintainer release commands:

```powershell
$env:RELEASE_STRICT = "1"
python scripts/build_portable_bundle.py
python scripts/verify_portable_release.py --repo . --portable-root dist/portable_bundle --zip dist/portable_bundle.zip --strict --json-out reports/verify_portable_release.json
```

To refresh the local direct-run folder from source:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync_portable_local.ps1
```

The build creates release metadata:

- `release_manifest.json`
- optional archive checksum when you build a zip yourself

Use the checksum file to verify an archive before distributing it.
