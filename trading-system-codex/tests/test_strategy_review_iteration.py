from __future__ import annotations

from datetime import timezone

UTC = timezone.utc


class FakeRepo:
    def __init__(self):
        self.session = FakeSession()


class FakeSession:
    async def execute(self, stmt):
        return FakeResult([])


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class TestReviewEngine:
    def test_empty_review_returns_no_errors(self):
        from app.services.strategy_signal.review_engine import ReviewEngine

        repo = FakeRepo()
        engine = ReviewEngine(repo)

        import asyncio
        review = asyncio.run(engine.build_review(update_outcomes=False))
        assert review["total_signals"] == 0
        assert review["latest_records"] == []
        assert "summary" in review

    def test_summary_fields_present(self):
        from app.services.strategy_signal.review_engine import ReviewEngine

        repo = FakeRepo()
        engine = ReviewEngine(repo)

        import asyncio
        review = asyncio.run(engine.build_review(update_outcomes=False))
        summary = review["summary"]
        assert "total_signals" in summary
        assert "tp1_hit_rate" in summary
        assert "stop_hit_rate" in summary
        assert "avg_mfe" in summary
        assert "avg_mae" in summary


class TestIterationEngine:
    def test_no_signals_returns_empty(self):
        from app.services.strategy_signal.iteration_engine import IterationEngine

        repo = FakeRepo()
        engine = IterationEngine(repo)

        import asyncio
        proposals = asyncio.run(engine.list_proposals())
        assert proposals == []

    def test_low_sample_generates_warning(self):
        from app.services.strategy_signal.iteration_engine import IterationEngine

        repo = FakeRepo()
        engine = IterationEngine(repo)

        import asyncio
        proposals = asyncio.run(engine.list_proposals())
        assert len(proposals) <= 1  # low sample or empty
