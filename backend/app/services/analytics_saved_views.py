from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.analytics_saved_view import AnalyticsSavedView
from app.schemas.analytics_catalog import AnalyticsCatalogRunRequest
from app.schemas.analytics_saved_view import AnalyticsSavedViewCreate, AnalyticsSavedViewRead
from app.services.analytics_bi import AnalyticsBIError
from app.services.analytics_catalog import materialize_catalog_request, validate_catalog_request


class AnalyticsSavedViewError(ValueError):
    pass


class AnalyticsSavedViewConflictError(AnalyticsSavedViewError):
    pass


def _name_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip()).casefold()
    return normalized


def _read(model: AnalyticsSavedView) -> AnalyticsSavedViewRead:
    return AnalyticsSavedViewRead(
        id=model.id,
        workspace_id=model.workspace_id,
        created_by_user_id=model.created_by_user_id,
        name=model.name,
        analysis_key=model.analysis_key,
        request=AnalyticsCatalogRunRequest.model_validate(model.request_json),
        chart=model.chart,
        display_mode=model.display_mode,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def list_analytics_saved_views(
    db: Session,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID,
    limit: int = 20,
) -> list[AnalyticsSavedViewRead]:
    rows = list(
        db.scalars(
            select(AnalyticsSavedView)
            .where(
                AnalyticsSavedView.workspace_id == workspace_id,
                AnalyticsSavedView.created_by_user_id == created_by_user_id,
            )
            .order_by(AnalyticsSavedView.updated_at.desc(), AnalyticsSavedView.id.desc())
            .limit(max(1, min(limit, 50)))
        )
    )
    return [_read(row) for row in rows]


def create_analytics_saved_view(
    db: Session,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID,
    payload: AnalyticsSavedViewCreate,
) -> AnalyticsSavedViewRead:
    try:
        definition = validate_catalog_request(
            db,
            workspace_id=workspace_id,
            request=payload.request,
        )
    except AnalyticsBIError as exc:
        raise AnalyticsSavedViewError(str(exc)) from exc

    request = materialize_catalog_request(definition, payload.request)
    chart = payload.chart or definition.default_chart
    if chart not in definition.supported_charts:
        raise AnalyticsSavedViewError("Saved chart is not supported by this analysis.")
    if chart == "table":
        # A table chart has no separate visual renderer; normalize the preference
        # rather than persisting a display mode that can never render.
        display_mode = "table"
    else:
        display_mode = payload.display_mode

    model = AnalyticsSavedView(
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        name=payload.name,
        name_key=_name_key(payload.name),
        analysis_key=request.analysis_key,
        request_json=request.model_dump(mode="json"),
        chart=chart,
        display_mode=display_mode,
    )
    db.add(model)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AnalyticsSavedViewConflictError("A saved analytics view with this name already exists.") from exc
    db.refresh(model)
    return _read(model)


def delete_analytics_saved_view(
    db: Session,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID,
    view_id: UUID,
) -> bool:
    result = db.execute(
        delete(AnalyticsSavedView).where(
            AnalyticsSavedView.workspace_id == workspace_id,
            AnalyticsSavedView.created_by_user_id == created_by_user_id,
            AnalyticsSavedView.id == view_id,
        )
    )
    if not result.rowcount:
        db.rollback()
        return False
    db.commit()
    return True
