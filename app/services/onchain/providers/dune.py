from __future__ import annotations


class DuneSnapshotProvider:
    provider_key = "dune"
    enabled_by_default = False
    auth_env = "DUNE_API_KEY"
    role = "cached_query_snapshot"
