from pathlib import Path


def test_startup_warmup_rebuilds_source_data_before_final_snapshot() -> None:
    text = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    source_call = text.index("await warm_local_market_data(")
    final_snapshot = text.index('reason="startup_strategy_snapshot_finalize"')
    assert source_call < final_snapshot
    assert "async with db_manager.writer_session() as session:" in text


def test_background_writers_use_full_transaction_writer_gate() -> None:
    root = Path(__file__).parents[1] / "app"
    files = (
        root / "workers" / "indicator_monitor.py",
        root / "workers" / "market_events_feed.py",
        root / "workers" / "market_event_translation.py",
        root / "workers" / "precompute_worker.py",
        root / "events" / "bus.py",
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "db_manager.writer_session()" in text, path
        assert "db_manager.session()" not in text, path


def test_alert_cooldown_normalizes_sqlite_naive_timestamp() -> None:
    text = (
        Path(__file__).parents[1] / "app" / "services" / "indicator_monitoring.py"
    ).read_text(encoding="utf-8")
    assert "recent.triggered_at.replace(tzinfo=UTC)" in text


def test_unified_warmup_is_queued_after_dependencies() -> None:
    text = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    plan = text.split("STRATEGY_CRITICAL_WARMUP_PLAN =", 1)[1].split(")\n\n", 1)[0]
    assert "strategy_unified" not in plan
    btc = text.index('current_page="btc-derivatives"')
    unified = text.index('candidates=["strategy_unified"]')
    assert btc < unified
