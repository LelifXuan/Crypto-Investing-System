"""Static guards: WS disconnect must evict the stream's instrument marks.

2026-09-22 price-lag fix: when the spot or futures websocket closes, the
worker used to sleep-and-reconnect while the in-memory market_cache kept
whatever mark_price the last successful push had written. With a silently
dead stream and no eviction, that residue could outlive a deployment and
be served to the next /market-prices/marks/latest caller — labeled as
"实时" by the chip. The fix:

- ``MarketStreamWorker._run_spot`` / ``_run_futures`` must call
  ``market_cache.clear_marks(self._instrument_ids)`` on
  ``ConnectionClosed`` (but NOT on generic Exception — a single bad frame
  should not blank the whole cache).
- The eviction must happen BEFORE the reconnect sleep, so a fresh fetch
  triggered during the backoff sees a clean cache.

These guards are read-only assertions on the worker source; the runtime
behaviour is exercised by ``tests/test_market_cache.py`` and the
``MarketService`` LKG tests.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = (ROOT / "app/workers/realtime_market.py").read_text(encoding="utf-8")


def _spot_block() -> str:
    start = WORKER.index("async def _run_spot(")
    end = WORKER.index("async def _run_futures(")
    return WORKER[start:end]


def _futures_block() -> str:
    start = WORKER.index("async def _run_futures(")
    end = WORKER.index("async def _subscribe_spot(")
    return WORKER[start:end]


def test_eviction_helper_exists_and_targets_clear_marks() -> None:
    assert "async def _evict_market_cache_on_disconnect(" in WORKER
    assert "await market_cache.clear_marks(instrument_ids)" in WORKER


def test_spot_disconnect_evicts_cache_before_reconnect_sleep() -> None:
    block = _spot_block()
    connclosed_idx = block.index("ConnectionClosed as exc")
    # The eviction must run while still inside the except arm, before the
    # asyncio.sleep that backs off the reconnect.
    evict_idx = block.index("_evict_market_cache_on_disconnect(")
    sleep_idx = block.index(
        "asyncio.sleep(settings.market_stream_reconnect_delay_seconds)",
        connclosed_idx,
    )
    assert evict_idx > connclosed_idx
    assert evict_idx < sleep_idx


def test_futures_disconnect_evicts_cache_before_reconnect_sleep() -> None:
    block = _futures_block()
    connclosed_idx = block.index("ConnectionClosed as exc")
    evict_idx = block.index("_evict_market_cache_on_disconnect(")
    sleep_idx = block.index(
        "asyncio.sleep(settings.market_stream_reconnect_delay_seconds)",
        connclosed_idx,
    )
    assert evict_idx > connclosed_idx
    assert evict_idx < sleep_idx


def test_generic_exception_branch_does_not_evict_cache() -> None:
    """A transient parse error in one frame must not blank the entire
    cache — only a real ConnectionClosed signals "the stream is dead,
    everything it last wrote is now residue"."""
    spot_block = _spot_block()
    futures_block = _futures_block()
    assert "except Exception as exc" in spot_block
    assert "except Exception as exc" in futures_block
    # The eviction call must live strictly inside the ConnectionClosed arm
    # of each run loop, not inside the generic Exception arm. We slice
    # until the next 'except' or end of run-loop body, whichever comes first.
    for block in (spot_block, futures_block):
        generic_idx = block.index("except Exception as exc")
        # Limit the slice to the Exception arm itself (until the next
        # "async def" defining a sibling method, or end of string).
        end_markers = [
            block.find("\n    async def ", generic_idx + 1),
            len(block),
        ]
        end_idx = min(pos for pos in end_markers if pos > 0)
        arm = block[generic_idx:end_idx]
        assert "_evict_market_cache_on_disconnect(" not in arm, (
            "generic Exception branch must not call cache eviction; "
            f"arm slice: {arm!r}"
        )