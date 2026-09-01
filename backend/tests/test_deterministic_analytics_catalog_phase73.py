from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.analytics_catalog import AnalyticsCatalogRunRequest
from app.services.analytics_bi import AnalyticsBIError
from app.services.analytics_catalog import _BY_KEY, _DEFINITIONS, run_catalog_analysis
from tests.test_deterministic_analytics_catalog_phase72 import NOW, _engine, _metrics, _seed


def _add_appointment(db: Session, ids: dict, *, patient: str, service: str, status: str, at: str, source: str = "phone") -> None:
    aid = uuid4()
    db.execute(
        text(
            """
            INSERT INTO appointments (id,workspace_id,patient_id,branch_id,doctor_id,service_id,status,source,start_at,end_at,created_at,updated_at)
            VALUES (:id,:w,:p,:b,:d,:s,:status,:source,:at,:at,:at,:at)
            """
        ),
        {
            "id": aid.hex,
            "w": ids["workspace"].hex,
            "p": ids[patient].hex,
            "b": ids["branch"].hex,
            "d": ids["doctor"].hex,
            "s": ids[service].hex,
            "status": status,
            "source": source,
            "at": at,
        },
    )


def _seed_phase73(db: Session):
    ids = _seed(db)
    # Mona: three completed Laser visits. Laila: two completed PRP visits.
    _add_appointment(db, ids, patient="recent", service="laser", status="completed", at="2026-08-17T18:00:00+00:00")
    _add_appointment(db, ids, patient="recent", service="laser", status="completed", at="2026-08-24T18:00:00+00:00")
    _add_appointment(db, ids, patient="other", service="prp", status="completed", at="2026-08-20T17:00:00+00:00")
    # Risk-pattern rows. Monday 18:00 has one no-show in addition to two completed visits.
    _add_appointment(db, ids, patient="old", service="laser", status="no_show", at="2026-08-24T18:00:00+00:00")
    # Tuesday 19:00 is a cancelled-only slot, so cancellation rate is 100% there.
    _add_appointment(db, ids, patient="old", service="laser", status="cancelled", at="2026-08-25T19:00:00+00:00")
    db.commit()
    return ids


def _run(db: Session, ids: dict, key: str, **kwargs):
    return run_catalog_analysis(
        db,
        workspace_id=ids["workspace"],
        request=AnalyticsCatalogRunRequest(analysis_key=key, **kwargs),
        now=NOW,
    )


def test_phase73_adds_complete_operational_and_retention_library() -> None:
    keys = {definition.key for definition in _DEFINITIONS}
    assert len(_DEFINITIONS) == 35
    assert {
        "appointment_peak_weekdays",
        "appointment_peak_hours",
        "no_show_peak_times",
        "cancellation_peak_times",
        "second_visit_conversion",
        "third_visit_conversion",
        "time_to_return",
        "time_to_return_by_service",
        "branch_retention",
        "lapsed_rate",
    }.issubset(keys)
    assert _BY_KEY["appointment_peak_hours"].default_chart == "heatmap"
    assert _BY_KEY["no_show_peak_times"].default_chart == "heatmap"
    assert _BY_KEY["lapsed_rate"].default_inactivity_days == 180


def test_peak_weekday_and_hour_analyses_are_database_aggregated() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed_phase73(db)
        weekday = _run(db, ids, "appointment_peak_weekdays", lookback_days=30)
        assert weekday.rows[0].label == "الاثنين"
        assert _metrics(weekday.rows[0])["appointments"] == 4
        assert weekday.highlights[0].key == "appointments"

        heatmap = _run(db, ids, "appointment_peak_hours", lookback_days=30)
        assert heatmap.chart == "heatmap"
        assert "18:00" in heatmap.chart_data.labels
        monday = next(series for series in heatmap.chart_data.series if series.label == "الاثنين")
        hour_index = heatmap.chart_data.labels.index("18:00")
        assert monday.values[hour_index] == 3.0
        assert len(heatmap.chart_data.series) == 7


def test_no_show_and_cancellation_heatmaps_use_explicit_rate_definitions() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed_phase73(db)
        no_show = _run(db, ids, "no_show_peak_times", lookback_days=30)
        monday = next(series for series in no_show.chart_data.series if series.label == "الاثنين")
        idx = no_show.chart_data.labels.index("18:00")
        assert monday.values[idx] == 33.3
        assert any("completed + no_show" in item for item in no_show.definitions)

        cancelled = _run(db, ids, "cancellation_peak_times", lookback_days=30)
        tuesday = next(series for series in cancelled.chart_data.series if series.label == "الثلاثاء")
        idx = cancelled.chart_data.labels.index("19:00")
        assert tuesday.values[idx] == 100.0
        assert any("cancelled" in item for item in cancelled.definitions)


def test_second_and_third_visit_conversion_are_distinct_from_repeat_rate() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed_phase73(db)
        second = _run(db, ids, "second_visit_conversion", lookback_days=365)
        third = _run(db, ids, "third_visit_conversion", lookback_days=365)
        second_metrics = _metrics(second.rows[0])
        third_metrics = _metrics(third.rows[0])
        assert second_metrics["patients_with_completed_visit"] == 3
        assert second_metrics["patients_with_second_visit"] == 2
        assert second_metrics["second_visit_conversion_rate"] == 66.7
        assert third_metrics["patients_with_third_visit"] == 1
        assert third_metrics["third_visit_conversion_rate"] == 33.3


def test_time_to_return_uses_sql_window_ordering_and_reports_median_and_average() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed_phase73(db)
        result = _run(db, ids, "time_to_return", lookback_days=365)
        metrics = _metrics(result.rows[0])
        assert metrics["median_days_to_second_visit"] == 7.8
        assert metrics["avg_days_to_second_visit"] == 7.8
        assert metrics["patients_with_second_visit"] == 2
        assert any("median" in item for item in result.definitions)

        by_service = _run(db, ids, "time_to_return_by_service", lookback_days=365, limit=10)
        labels = [row.label for row in by_service.rows]
        assert labels == ["Laser", "PRP"]
        values = {row.label: _metrics(row) for row in by_service.rows}
        assert values["Laser"]["median_days_to_second_visit"] == 7.3
        assert values["PRP"]["median_days_to_second_visit"] == 8.3


def test_lapsed_rate_matches_lapsed_definition_without_loading_patient_list() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed_phase73(db)
        result = _run(db, ids, "lapsed_rate", all_history=True, inactivity_days=180)
        metrics = _metrics(result.rows[0])
        assert metrics["patients_with_completed_visit"] == 3
        assert metrics["lapsed_patients"] == 1
        assert metrics["lapsed_rate"] == 33.3


def test_branch_retention_is_a_real_grouped_analysis() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed_phase73(db)
        result = _run(db, ids, "branch_retention", lookback_days=365)
        assert result.business_plan is not None
        assert result.business_plan.group_by == ["branch"]
        metrics = _metrics(result.rows[0])
        assert metrics["repeat_patients"] == 2
        assert metrics["repeat_rate"] == 66.7


def test_special_analytics_reject_unknown_canonical_filter_ids() -> None:
    engine = _engine()
    with Session(engine) as db:
        ids = _seed_phase73(db)
        with pytest.raises(AnalyticsBIError, match="unknown canonical service"):
            _run(
                db,
                ids,
                "appointment_peak_hours",
                lookback_days=30,
                service_ids=[str(uuid4())],
            )


def test_frontend_has_heatmap_renderer_without_client_side_patient_aggregation() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "frontend/src/app/(dashboard)/analytics/catalog.tsx").read_text(encoding="utf-8")
    types = (root / "frontend/src/lib/types.ts").read_text(encoding="utf-8")
    assert 'heatmap: "خريطة حرارية"' in source
    assert "function HeatmapVisualization" in source
    assert 'chartType === "heatmap"' in source
    assert '"heatmap"' in types
