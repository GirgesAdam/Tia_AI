from __future__ import annotations

import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin
from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.database.session import get_db
from app.schemas.whatsapp_setup import (
    WhatsAppEmbeddedSignupComplete,
    WhatsAppEmbeddedSignupConfig,
    WhatsAppEmbeddedSignupResult,
    WhatsAppSetupState,
)
from app.services.meta_whatsapp_onboarding import (
    MetaWhatsAppConfigurationError,
    MetaWhatsAppConflictError,
    MetaWhatsAppProviderError,
    build_whatsapp_setup_state,
    complete_embedded_signup,
    embedded_signup_public_config,
)
from app.services.meta_whatsapp_transport import (
    ingest_meta_webhook,
    run_meta_transport_tick,
    verify_meta_webhook_challenge,
    verify_meta_webhook_signature,
)

router = APIRouter()


@router.get("/webhook", include_in_schema=False)
def whatsapp_meta_webhook_verify(
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    if challenge is None or not verify_meta_webhook_challenge(mode, verify_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Meta webhook verification.")
    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook", include_in_schema=False)
async def whatsapp_meta_webhook_receive(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_hub_signature_256: Annotated[
        str | None, Header(alias="X-Hub-Signature-256")
    ] = None,
) -> dict[str, int | bool]:
    body = await request.body()
    if not verify_meta_webhook_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Meta webhook signature.")
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Meta webhook JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Meta webhook payload.")
    result = ingest_meta_webhook(db, payload)
    return {"received": True, **result}


def _require_transport_worker(
    x_tia_transport_token: Annotated[
        str | None, Header(alias="X-Tia-Transport-Token")
    ] = None,
) -> None:
    expected = meta_whatsapp_settings.channel_transport_worker_token
    if not expected or not expected.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tia WhatsApp transport worker is not configured.",
        )
    supplied = (x_tia_transport_token or "").strip()
    if not supplied or not hmac.compare_digest(supplied, expected.strip()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid transport worker token.")


@router.post("/transport/tick")
def whatsapp_transport_tick(
    _worker: Annotated[None, Depends(_require_transport_worker)],
    db: Annotated[Session, Depends(get_db)],
    limit_per_connection: Annotated[int, Query(ge=1, le=50)] = 10,
    max_connections: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, int]:
    return run_meta_transport_tick(
        db,
        limit_per_connection=limit_per_connection,
        max_connections=max_connections,
    )


@router.get("/setup", response_model=WhatsAppSetupState)
def whatsapp_setup_state(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> WhatsAppSetupState:
    return build_whatsapp_setup_state(db, workspace_id=access.workspace.id)


@router.get("/setup/embedded-signup/config", response_model=WhatsAppEmbeddedSignupConfig)
def whatsapp_embedded_signup_config(
    _access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
) -> WhatsAppEmbeddedSignupConfig:
    return embedded_signup_public_config()


@router.post(
    "/setup/embedded-signup/complete",
    response_model=WhatsAppEmbeddedSignupResult,
)
def whatsapp_embedded_signup_complete(
    payload: WhatsAppEmbeddedSignupComplete,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> WhatsAppEmbeddedSignupResult:
    try:
        state = complete_embedded_signup(
            db,
            workspace_id=access.workspace.id,
            created_by_user_id=access.user.id,
            code=payload.code,
            waba_id=payload.waba_id,
            phone_number_id=payload.phone_number_id,
            business_id=payload.business_id,
        )
    except MetaWhatsAppConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except MetaWhatsAppConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except MetaWhatsAppProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return WhatsAppEmbeddedSignupResult(state=state)
