from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import CurrentUser, require_roles
from app.core.local_secrets import secret_store
from app.schemas.common import MessageResponse
from app.schemas.local_secrets import GateCredentialsStatusResponse, GateCredentialsUpsertRequest

router = APIRouter(prefix="/local-secrets", tags=["local-secrets"])


@router.get("/gate", response_model=GateCredentialsStatusResponse)
async def get_gate_secret_status(_: CurrentUser = Depends(require_roles("admin"))) -> GateCredentialsStatusResponse:
    status_payload = secret_store.gate_credentials_status()
    return GateCredentialsStatusResponse(
        configured=bool(status_payload["configured"]),
        updated_at=status_payload["updated_at"],
        label=status_payload["label"],
        storage_path=str(secret_store.store_path),
        key_path=str(secret_store.key_path),
    )


@router.put("/gate", response_model=GateCredentialsStatusResponse)
async def upsert_gate_secret(
    payload: GateCredentialsUpsertRequest,
    _: CurrentUser = Depends(require_roles("admin")),
) -> GateCredentialsStatusResponse:
    status_payload = secret_store.save_gate_credentials(
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        passphrase=payload.passphrase,
        label=payload.label,
    )
    return GateCredentialsStatusResponse(
        configured=True,
        updated_at=status_payload["updated_at"],
        label=status_payload["label"],
        storage_path=str(secret_store.store_path),
        key_path=str(secret_store.key_path),
    )


@router.delete("/gate", response_model=MessageResponse)
async def delete_gate_secret(_: CurrentUser = Depends(require_roles("admin"))) -> MessageResponse:
    deleted = secret_store.delete_gate_credentials()
    return MessageResponse(message="gate credentials deleted" if deleted else "gate credentials not configured")
