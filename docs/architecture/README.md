# Docs Guide

`docs/` stores architecture notes, cleanup decisions, operating references, and
release records for the local trading system.

## Current Structure

- `architecture.md`: current runtime architecture, module boundaries, entry
  points, frontend/backend layering, and high-complexity hotspots.
- `cleanup-audit.md`: evidence-based cleanup register for legacy wrappers,
  compatibility routes, generated artifacts, and refactor candidates.
- `CACHE_ARCHITECTURE.md`: cache layers and freshness responsibilities.
- `source-availability-matrix.md`: upstream data source status and caveats.
- `strategy-refactor-readiness.md`: historical strategy refactor decisions and
  compatibility risks.
- `domain-model.md`, `event-model.md`, `module-specs.md`: early domain design
  references. Treat them as background unless refreshed for the current code.
- `OPERATIONS.md`: local operation and maintenance notes.
- `CHANGELOG.md`: chronological product changes.
- `RELEASE.md`: release checklists and manual verification commands.
- `superpowers/`: archived implementation plans/specs. These are useful audit
  history, not current architecture source of truth.

## Documentation Rules

- Prefer updating `architecture.md` when a boundary or entrypoint changes.
- Add cleanup decisions to `cleanup-audit.md` before deleting compatibility code.
- Keep release notes in `CHANGELOG.md` / `RELEASE.md`, not in source comments.
- Do not store runtime logs, screenshots, cache files, or portable build outputs
  here unless they are intentional fixtures.
