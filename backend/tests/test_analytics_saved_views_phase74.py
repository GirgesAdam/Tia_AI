from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.schemas.analytics_catalog import AnalyticsCatalogRunRequest
from app.schemas.analytics_saved_view import AnalyticsSavedViewCreate
from app.services.analytics_catalog import run_catalog_analysis
from app.services.analytics_export import analytics_result_csv
from app.services.analytics_saved_views import (
    AnalyticsSavedViewError,
    create_analytics_saved_view,
    delete_analytics_saved_view,
    list_analytics_saved_views,
)
from tests.test_deterministic_analytics_catalog_phase72 import NOW, _engine, _seed


def _saved_view_engine():
    engine = _engine()
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE analytics_saved_views (
                id CHAR(32) PRIMARY KEY,
                workspace_id CHAR(32) NOT NULL,
                created_by_user_id CHAR(32) NOT NULL,
                name VARCHAR(160) NOT NULL,
                name_key VARCHAR(180) NOT NULL,
                analysis_key VARCHAR(120) NOT NULL,
                request JSON NOT NULL DEFAULT '{}',
                chart VARCHAR(16),
                display_mode VARCHAR(16) NOT NULL DEFAULT 'visual',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (workspace_id, created_by_user_id, name_key)
            )
            """
        )
    return engine


def test_saved_view_persists_effective_registry_defaults_not_result_snapshot() -> None:
    engine = _saved_view_engine()
    with Session(engine) as db:
        ids = _seed(db)
        creator = uuid4()
        view = create_analytics_saved_view(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=creator,
            payload=AnalyticsSavedViewCreate(
                name="  إيراد الخدمات   آخر 90 يوم ",
                request=AnalyticsCatalogRunRequest(analysis_key="revenue_by_service"),
                chart="bar",
                display_mode="both",
            ),
        )
        assert view.name == "إيراد الخدمات آخر 90 يوم"
        assert view.created_by_user_id == creator
        assert view.analysis_key == "revenue_by_service"
        assert view.request.lookback_days == 90
        assert view.request.limit == 10
        assert view.chart == "bar"
        assert view.display_mode == "both"

        # Only configuration is persisted. Re-running the stored request uses the
        # current canonical database and deterministic executor.
        result = run_catalog_analysis(
            db,
            workspace_id=ids["workspace"],
            request=view.request,
            now=NOW,
        )
        assert result.request.lookback_days == 90
        assert [row.label for row in result.rows] == ["PRP", "Laser"]


def test_saved_view_rejects_unknown_filters_entities_and_duplicate_names() -> None:
    engine = _saved_view_engine()
    with Session(engine) as db:
        ids = _seed(db)
        with pytest.raises(AnalyticsSavedViewError, match="does not accept the service filter"):
            create_analytics_saved_view(
                db,
                workspace_id=ids["workspace"],
                created_by_user_id=uuid4(),
                payload=AnalyticsSavedViewCreate(
                    name="Bad filter",
                    request=AnalyticsCatalogRunRequest(
                        analysis_key="revenue_overview",
                        service_ids=[str(ids["laser"])],
                    ),
                ),
            )
        with pytest.raises(AnalyticsSavedViewError, match="unknown canonical service"):
            create_analytics_saved_view(
                db,
                workspace_id=ids["workspace"],
                created_by_user_id=uuid4(),
                payload=AnalyticsSavedViewCreate(
                    name="Bad entity",
                    request=AnalyticsCatalogRunRequest(
                        analysis_key="revenue_trend",
                        service_ids=[str(uuid4())],
                    ),
                ),
            )

        payload = AnalyticsSavedViewCreate(
            name="Revenue view",
            request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview"),
        )
        owner = uuid4()
        create_analytics_saved_view(
            db, workspace_id=ids["workspace"], created_by_user_id=owner, payload=payload
        )
        with pytest.raises(AnalyticsSavedViewError, match="already exists"):
            create_analytics_saved_view(
                db,
                workspace_id=ids["workspace"],
                created_by_user_id=owner,
                payload=AnalyticsSavedViewCreate(
                    name="  REVENUE   VIEW ",
                    request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview"),
                ),
            )


def test_saved_views_are_workspace_and_user_scoped_and_delete_is_scoped() -> None:
    engine = _saved_view_engine()
    with Session(engine) as db:
        ids = _seed(db)
        owner = uuid4()
        other_user = uuid4()
        other_workspace = uuid4()
        first = create_analytics_saved_view(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=owner,
            payload=AnalyticsSavedViewCreate(
                name="My main workspace view",
                request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview"),
            ),
        )
        create_analytics_saved_view(
            db,
            workspace_id=ids["workspace"],
            created_by_user_id=other_user,
            payload=AnalyticsSavedViewCreate(
                name="Other user's view",
                request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview"),
            ),
        )
        create_analytics_saved_view(
            db,
            workspace_id=other_workspace,
            created_by_user_id=owner,
            payload=AnalyticsSavedViewCreate(
                name="Other workspace",
                request=AnalyticsCatalogRunRequest(analysis_key="revenue_overview"),
            ),
        )
        current = list_analytics_saved_views(
            db, workspace_id=ids["workspace"], created_by_user_id=owner
        )
        assert [item.name for item in current] == ["My main workspace view"]
        assert delete_analytics_saved_view(
            db, workspace_id=ids["workspace"], created_by_user_id=other_user, view_id=first.id
        ) is False
        assert delete_analytics_saved_view(
            db, workspace_id=other_workspace, created_by_user_id=owner, view_id=first.id
        ) is False
        assert delete_analytics_saved_view(
            db, workspace_id=ids["workspace"], created_by_user_id=owner, view_id=first.id
        ) is True
        assert list_analytics_saved_views(
            db, workspace_id=ids["workspace"], created_by_user_id=owner
        ) == []


def test_backend_csv_export_reexecutes_typed_result_and_formats_money_as_major_units() -> None:
    engine = _saved_view_engine()
    with Session(engine) as db:
        ids = _seed(db)
        result = run_catalog_analysis(
            db,
            workspace_id=ids["workspace"],
            request=AnalyticsCatalogRunRequest(
                analysis_key="revenue_by_service", lookback_days=30
            ),
            now=NOW,
        )
        csv_text = analytics_result_csv(result).decode("utf-8-sig")
        assert "الاسم" in csv_text
        assert "صافي" in csv_text
        assert "PRP" in csv_text and "Laser" in csv_text
        assert "1500.0" in csv_text
        assert "1000.0" in csv_text
        # The 90,000 EGP unallocated transaction in the fixture must never leak
        # into a service-attributed revenue export.
        assert "90000" not in csv_text


def test_phase74_routes_frontend_and_migration_use_deterministic_saved_view_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    routes = (root / "app/api/routes/analytics.py").read_text(encoding="utf-8")
    view_routes = (root / "app/api/routes/analytics_views.py").read_text(encoding="utf-8")
    router = (root / "app/api/router.py").read_text(encoding="utf-8")
    service = (root / "app/services/analytics_saved_views.py").read_text(encoding="utf-8")
    migration = (root / "alembic/versions/0042_analytics_saved_views.py").read_text(encoding="utf-8")
    readiness = (root / "app/services/operational_readiness.py").read_text(encoding="utf-8")
    frontend_root = root.parent / "frontend/src"
    catalog = (frontend_root / "app/(dashboard)/analytics/catalog.tsx").read_text(encoding="utf-8")
    page = (frontend_root / "app/(dashboard)/analytics/page.tsx").read_text(encoding="utf-8")
    proxy = (frontend_root / "app/api/analytics/export/route.ts").read_text(encoding="utf-8")

    assert '@router.get("/views"' in view_routes
    assert '@router.post("/views"' in view_routes
    assert '@router.delete("/views/{view_id}"' in view_routes
    assert "analytics_views_router" in router
    assert '@router.post("/catalog/export")' in routes
    assert '@router.delete(' not in routes
    assert "run_catalog_analysis" in routes
    assert "materialize_catalog_request" in service
    model = (root / "app/models/analytics_saved_view.py").read_text(encoding="utf-8")
    assert "request_json" in model
    assert "result_json" not in model and "rows_json" not in model
    assert 'revision: str = "0042_analytics_saved_views"' in migration
    assert 'down_revision: str | None = "0041_analytics_query_indexes"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL" in migration
    assert "created_by_user_id" in migration and "ondelete=\"CASCADE\"" in migration
    assert 'EXPECTED_MIGRATION_HEAD = "0053_public_table_rls_completion"' in readiness
    assert 'tiaRequest<AnalyticsSavedView[]>("/analytics/views?limit=20")' in page
    assert "savedViews.length > 0" in catalog
    assert "savedViews.map" in catalog
    assert "حفظ العرض" in catalog
    assert 'fetch("/api/analytics/export"' in catalog
    assert 'tiaRawRequest("/analytics/catalog/export"' in proxy
    assert "exportCsv(result" not in catalog
