from __future__ import annotations

from app.services.agent_v2.outcome_builder import _service_catalog_facts
from app.services.agent_v2.read_executor import ReadResult


def _service_result(**service: object) -> ReadResult:
    return ReadResult(
        kind="service_catalog",
        ok=True,
        payload={"service": {"name": "استشارة جلدية أو ليزر", **service}},
    )


def test_requested_duration_falls_back_to_canonical_duration_minutes() -> None:
    facts = _service_catalog_facts(
        _service_result(duration_minutes=30),
        {"duration"},
    )

    assert facts == {
        "service": {
            "name": "استشارة جلدية أو ليزر",
            "duration_minutes": 30,
        }
    }


def test_customer_duration_text_takes_precedence_when_adapter_supplies_it() -> None:
    facts = _service_catalog_facts(
        _service_result(duration_minutes=30, customer_duration_text="حوالي نص ساعة"),
        {"duration"},
    )

    assert facts["service"]["customer_duration_text"] == "حوالي نص ساعة"
    assert "duration_minutes" not in facts["service"]


def test_duration_is_not_exposed_when_customer_did_not_request_it() -> None:
    facts = _service_catalog_facts(
        _service_result(duration_minutes=30),
        {"price"},
    )

    assert "duration_minutes" not in facts["service"]
