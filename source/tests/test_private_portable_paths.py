from scripts.build_private_portable import START, include_source


def test_private_bundle_source_and_runtime_cache_are_distinct():
    for name in [
        "source/app/cache/market_cache.py",
        "source/app/static/ui/commandPalette.js",
        "source/app/static/core/workbenchState.js",
        "source/.env.example",
        "source/data/cftc/gold_history.json",
    ]:
        assert include_source(name), name
    for name in [
        "nul",
        "source/runtime/cache/a.json",
        "source/runtime/data/a.db",
        "source/tests/screenshots/a.png",
        "source/.env",
        "dist/old.zip",
    ]:
        assert not include_source(name), name
    assert 'set "APP_RUNTIME_ROOT=%~dp0source\\runtime"' in START
    assert 'set "DATABASE_URL=' in START
