from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin
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

router = APIRouter()


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
