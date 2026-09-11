from types import SimpleNamespace

from app.agents.turn_interpreter import (
    UnifiedTurnDecision,
    _normalize_single_location_decision,
    _option_summary,
    _semantic_catalog_for_single_location,
)
from app.agents.turn_models import SemanticEntityHints


def _hints() -> SemanticEntityHints:
    return SemanticEntityHints.model_validate(
        {
            "service_query": "underarm laser",
            "branch_query": "Nasr City",
            "doctor_query": "Ahmed",
            "service_id": "service-1",
            "service_candidate_ids": [],
            "branch_id": "branch-1",
            "branch_candidate_ids": ["branch-2"],
            "doctor_id": "doctor-1",
            "doctor_candidate_ids": [],
            "requested_date": "2026-09-08",
            "requested_start_time": "20:00",
            "not_before_time": None,
            "not_after_time": None,
            "appointment_reference": None,
        }
    )


def _decision() -> UnifiedTurnDecision:
    return UnifiedTurnDecision.model_validate(
        {
            "domains": ["booking"],
            "capabilities": [
                "appointment_creation",
                "availability_discovery",
                "branch_discovery",
            ],
            "risk_flags": [],
            "flow_signal": "start_booking",
            "package_intent": "none",
            "action": "continue",
            "entity_hints": _hints().model_dump(mode="json"),
            "clear_entity_fields": ["branch_id", "requested_start_time"],
            "selection_index": None,
            "selection_time": None,
            "missing_information": ["branch", "doctor"],
            "recommended_handoff_category": "other",
            "recommended_handoff_priority": "normal",
            "confidence": 0.92,
            "reason": "Booking request",
        }
    )


def test_semantic_catalog_hides_storage_location_rows() -> None:
    catalog = {
        "services": [
            {"id": "service-1", "name": "Underarm Laser", "doctor_ids": ["doctor-1"]}
        ],
        "branches": [{"id": "branch-1", "name": "Internal location"}],
        "doctors": [
            {
                "id": "doctor-1",
                "name": "Ahmed",
                "service_ids": ["service-1"],
                "branch_ids": ["branch-1"],
                "scheduled_branch_ids": ["branch-1"],
            }
        ],
    }

    semantic = _semantic_catalog_for_single_location(catalog)

    assert "branches" not in semantic
    assert "doctor_ids" not in semantic["services"][0]
    assert "branch_ids" not in semantic["doctors"][0]
    assert "scheduled_branch_ids" not in semantic["doctors"][0]
    assert "branches" in catalog
    assert "branch_ids" in catalog["doctors"][0]


def test_single_location_normalization_removes_branch_semantics() -> None:
    result = _normalize_single_location_decision(_decision())

    assert "branch_discovery" not in result.capabilities
    assert result.entity_hints.branch_query is None
    assert result.entity_hints.branch_id is None
    assert result.entity_hints.branch_candidate_ids == []
    assert result.clear_entity_fields == ["requested_start_time"]
    assert result.missing_information == ["doctor"]
    assert result.entity_hints.service_id == "service-1"
    assert result.entity_hints.doctor_id == "doctor-1"


def test_presented_options_do_not_expose_branch_names_or_branch_choices() -> None:
    flow = SimpleNamespace(
        option_snapshot={
            "slots": [
                {
                    "start_time_24h": "20:00",
                    "end_time_24h": "20:15",
                    "doctor_name": "Ahmed",
                    "branch_name": "Internal location",
                }
            ],
            "branches": [
                {"branch_id": "branch-1", "branch_name": "Internal location"}
            ],
            "services": [{"service_id": "service-1", "service_name": "Laser"}],
            "doctors": [{"doctor_id": "doctor-1", "doctor_name": "Ahmed"}],
        }
    )

    summary = _option_summary(flow)

    assert "branches" not in summary
    assert "branch_name" not in summary["slots"][0]
    assert summary["services"][0]["id"] == "service-1"
    assert summary["doctors"][0]["id"] == "doctor-1"


def test_semantic_catalog_drops_operational_and_duplicate_fields() -> None:
    catalog = {
        "services": [
            {
                "id": "service-1", "name": "HydraFacial", "category": "Skin",
                "description": "D" * 500, "duration_minutes": 60,
                "price_minor": 180000, "currency": "EGP", "price": "1,800 EGP",
                "requires_medical_review": False, "requires_laser_device": False,
                "doctor_ids": ["doctor-1"],
            },
            {
                "id": "service-2", "name": "Underarm Laser", "category": "Laser",
                "requires_laser_device": True, "doctor_ids": ["doctor-1"],
                "laser_devices": [{
                    "device_key": "candela_gentle", "device_name": "Candela Gentle",
                    "price_minor": 65000, "currency": "EGP", "configured": True,
                }],
            },
        ],
        "branches": [{"id": "branch-1", "working_hours": [{"weekday": 1}]}],
        "doctors": [{
            "id": "doctor-1", "name": "Ahmed", "specialization": "Dermatology",
            "service_ids": ["service-1", "service-2"], "branch_ids": ["branch-1"],
            "working_hours": [{"weekday": 1, "start": "10:00", "end": "20:00"}],
        }],
        "appointments": [{
            "id": "appointment-1", "appointment_id": "appointment-1",
            "service_id": "service-1", "service_name": "HydraFacial",
            "doctor_id": "doctor-1", "doctor_name": "Ahmed", "status": "confirmed",
            "start_local": "2026-09-12T10:00:00+03:00",
            "end_local": "2026-09-12T11:00:00+03:00", "price_minor": 180000,
            "payment_status": "paid",
        }],
    }
    semantic = _semantic_catalog_for_single_location(catalog)
    assert "branches" not in semantic
    assert "doctor_ids" not in semantic["services"][0]
    assert "price_minor" not in semantic["services"][0]
    assert "duration_minutes" not in semantic["services"][0]
    assert len(semantic["services"][0]["description"]) == 240
    assert semantic["services"][1]["laser_devices"] == [
        {"device_key": "candela_gentle", "device_name": "Candela Gentle"}
    ]
    assert "working_hours" not in semantic["doctors"][0]
    assert "branch_ids" not in semantic["doctors"][0]
    assert "end_local" not in semantic["appointments"][0]
    assert "price_minor" not in semantic["appointments"][0]
    assert "branches" in catalog
    assert "working_hours" in catalog["doctors"][0]
