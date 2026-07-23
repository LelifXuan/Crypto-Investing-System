from __future__ import annotations

import pytest

from app.services.storage_maintenance import StorageMaintenanceService


@pytest.mark.asyncio
async def test_storage_maintenance_cleans_both_ttl_cache_tables() -> None:
    calls: list[str] = []

    class Repository:
        async def delete_expired_page_snapshot_cache(self, limit: int = 500) -> int:
            calls.append("page")
            return 7

        async def delete_expired_computed_dataset_cache(self, limit: int = 500) -> int:
            calls.append("dataset")
            return 11

    class Archive:
        def maintain(self):
            calls.append("archive")
            return object()

    report = await StorageMaintenanceService(Archive()).run(Repository())

    assert report.expired_page_snapshots == 7
    assert report.expired_datasets == 11
    assert calls == ["page", "dataset", "archive"]
