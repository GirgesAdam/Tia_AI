from app.agents.clinic_grounding import (
    _annotate_catalog_relationships,
    validate_grounded_entity_ids,
)
from app.agents.semantic_router import SemanticEntityHints


def _hints(**updates: object) -> SemanticEntityHints:
    payload: dict[str, object] = {
        "service_query": None,
        "branch_query": None,
        "doctor_query": None,
        "service_id": None,
        "service_candidate_ids": [],
        "branch_id": None,
        "branch_candidate_ids": [],
        "doctor_id": None,
        "doctor_candidate_ids": [],
        "requested_date": None,
        "requested_start_time": None,
        "not_before_time": None,
        "not_after_time": None,
        "appointment_reference": None,
    }
    payload.update(updates)
    return SemanticEntityHints.model_validate(payload)


def _catalog() -> dict[str, object]:
    return {
        "services": [
            {"id": "service-compatible", "name": "Compatible"},
            {"id": "service-incompatible", "name": "Incompatible"},
        ],
        "branches": [
            {"id": "branch-compatible", "name": "Compatible branch"},
            {"id": "branch-incompatible", "name": "Incompatible branch"},
        ],
        "doctors": [
            {
                "id": "doctor-1",
                "name": "Doctor One",
                "service_ids": ["service-compatible"],
                "branch_ids": ["branch-compatible"],
            }
        ],
    }


def test_catalog_relationships_mirror_doctor_ids_on_services() -> None:
    catalog = _annotate_catalog_relationships(_catalog())

    services = {row["id"]: row for row in catalog["services"]}
    assert services["service-compatible"]["doctor_ids"] == ["doctor-1"]
    assert services["service-incompatible"]["doctor_ids"] == []


def test_selected_doctor_resolves_one_compatible_service_candidate() -> None:
    result = validate_grounded_entity_ids(
        _hints(
            doctor_id="doctor-1",
            service_candidate_ids=["service-incompatible", "service-compatible"],
        ),
        _catalog(),
    )

    assert result.service_id == "service-compatible"
    assert result.service_candidate_ids == []


def test_selected_doctor_rejects_incompatible_selected_service() -> None:
    result = validate_grounded_entity_ids(
        _hints(doctor_id="doctor-1", service_id="service-incompatible"),
        _catalog(),
    )

    assert result.service_id is None
    assert result.service_candidate_ids == []


def test_selected_doctor_resolves_one_compatible_branch_candidate() -> None:
    result = validate_grounded_entity_ids(
        _hints(
            doctor_id="doctor-1",
            branch_candidate_ids=["branch-incompatible", "branch-compatible"],
        ),
        _catalog(),
    )

    assert result.branch_id == "branch-compatible"
    assert result.branch_candidate_ids == []
