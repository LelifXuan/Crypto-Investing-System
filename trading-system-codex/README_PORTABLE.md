# Trading System Source Portable Bundle

This package is a source portable bundle. It does not include an embedded Python runtime.

## Requirements

- Python 3.11 or Python 3.14 available on `PATH`
- Project dependencies installed in the Python environment used to launch the app
- Localhost access to the selected port, default `8000`

## Start

Windows:

```bat
start_portable.bat
```

Linux or macOS:

```bash
./start_portable.sh
```

The launcher creates runtime folders under `runtime/` on first start. Runtime data, logs,
SQLite databases, cache files, and generated `runtime/config/portable.env` are intentionally
not included in the release archive.

## Worker Profile

For offline troubleshooting, set:

```env
WORKER_PROFILE=none
```

Accepted disabled values are `none`, `off`, and `disabled`. Pages will still render local
snapshots and degraded states, but background workers will not start.

## Release Integrity

The build creates:

- `release_manifest.json`
- `portable_bundle.zip.sha256`

Use the checksum file to verify the zip before distributing it.
