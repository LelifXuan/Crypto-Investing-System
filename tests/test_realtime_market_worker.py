from __future__ import annotations

import json

import pytest

from app.workers.realtime_market import MarketStreamWorker


class DummyWebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, payload: str) -> None:
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_ping_loop_uses_requested_channel(monkeypatch) -> None:
    worker = MarketStreamWorker()
    ws = DummyWebSocket()

    async def fast_sleep(_: int) -> None:
        worker._stopping.set()

    monkeypatch.setattr("app.workers.realtime_market.asyncio.sleep", fast_sleep)

    await worker._ping_loop(ws, "futures.ping")

    assert len(ws.messages) == 1
    assert json.loads(ws.messages[0])["channel"] == "futures.ping"


def test_disconnect_description_without_close_frame() -> None:
    class DummyConnectionClosed(Exception):
        rcvd = None
        sent = None

    message = MarketStreamWorker._describe_disconnect(DummyConnectionClosed())  # type: ignore[arg-type]

    assert message == "connection closed without a close frame"
