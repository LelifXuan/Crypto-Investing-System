# Contributing

## Local Development

This repository is maintained as a Windows-first local application.

1. Use Python `3.11` or `3.14`.
2. Create and activate a virtual environment before running project tasks.
3. Copy `.env.example` to `.env` when you need local overrides.
4. Use `python scripts/tasks.py install` to install dependencies.
5. Prefer `python scripts/tasks.py check` before handing work off.

## Runtime Defaults

- Local single-user mode is the default and should remain the baseline.
- SQLite is the default database for local work.
- `127.0.0.1` is the default bind target for development.
- `desktop_light` is the default worker profile unless a change specifically needs more background work.

## Change Expectations

- Keep changes focused and easy to review.
- Do not commit secrets, local databases, logs, or generated caches.
- Add or update tests when behavior changes.
- Prefer recoverable failure handling and low-noise logging for background workers.

## Frontend Guardrails

- Keep browser-facing source files in UTF-8, especially `app/templates/*.html` and `app/static/**/*.js`.
- On Windows editors, verify the file encoding stays UTF-8 before saving Chinese copy.
- When page modules change, run `node --check app/static/pages/<page>.js` before handoff.
- New chart pages must always render one of three states: loading, empty, or error. Do not leave blank containers.
