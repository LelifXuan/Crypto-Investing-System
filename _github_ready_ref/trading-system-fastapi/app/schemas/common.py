from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class RebuildResponse(BaseModel):
    message: str
    account_id: str
    instrument_id: str | None = None
    cost_method: str
    updated: int


class TimestampedResponse(BaseModel):
    generated_at: datetime
