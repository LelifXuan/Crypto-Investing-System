from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StorageMaintenanceReport:
    expired_page_snapshots: int
    expired_datasets: int


class StorageMaintenanceService:
    def __init__(self, derivatives_archive: Any) -> None:
        self.derivatives_archive = derivatives_archive

    async def run(self, repository: Any) -> StorageMaintenanceReport:
        expired_pages = await repository.delete_expired_page_snapshot_cache(limit=500)
        expired_datasets = await repository.delete_expired_computed_dataset_cache(limit=500)
        self.derivatives_archive.maintain()
        return StorageMaintenanceReport(expired_pages, expired_datasets)
