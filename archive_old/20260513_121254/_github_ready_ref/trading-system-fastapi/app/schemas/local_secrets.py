from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GateCredentialsUpsertRequest(BaseModel):
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)
    passphrase: str | None = None
    label: str | None = None


class GateCredentialsStatusResponse(BaseModel):
    provider: str = "gateio"
    configured: bool
    updated_at: datetime | None = None
    label: str | None = None
    storage_path: str
    key_path: str
