from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.security import WorkspaceAccess, get_workspace_admin
from app.database.session import get_db
from app.schemas.operations import WorkspaceOperationalReadiness
from app.services.operational_readiness import build_workspace_operational_readiness


router = APIRouter()


@router.get("/readiness", response_model=WorkspaceOperationalReadiness)
def operational_readiness(
    access: Annotated[WorkspaceAccess, Depends(get_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkspaceOperationalReadiness:
    return build_workspace_operational_readiness(
        db,
        workspace_id=access.workspace.id,
    )
