from __future__ import annotations

import json

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.semantic_state_view import with_safe_read_context, with_safe_task_context

SERVICE_LASER = "11111111-1111-4111-8111-111111111111"
SERVICE_PRP = "22222222-2222-4222-8222-222222222222"
DOCTOR_A = "33333333-3333-4333-8333-333333333333"
DOCTOR_B = "44444444-4444-4444-8444-444444444444"
APPOINTMENT = "55555555-5555-4555-8555-555555555555"
PACKAGE = "66666666-6666-4666-8666-666666666666"


def _catalog() -> dict[str, object]:
    return {
        "services": [
            {
                "id": SERVICE_LASER,
                "name": "ليزر إبط",
                "category": "laser",
                "requires_laser_device": True,
                "laser_devices": [
                    {"device_key": "prime", "device_name": "Prime Lase"},
                    {"device_key": "candela", "device_name": "Candela Gentle"},
                ],
            },
            {
                "id": SERVICE_PRP,
                "name": "PRP للشعر",
                "category": "injectables",
                "laser_devices": [],
            },
        ],
        "doctors": [
            {
                "id": DOCTOR_A,
                "name": "د. مريم",
                "specialization": "Dermatology",
                "service_ids": [SERVICE_LASER, SERVICE_PRP],
            },
            {
                "id": DOCTOR_B,
                "name": "د. سارة",
                "specialization": "Dermatology",
                "service_ids": [SERVICE_LASER],
            },
        ],
        "appointments": [
            {
                "appointment_id": APPOINTMENT,
                "service_id": SERVICE_LASER,
                "doctor_id": DOCTOR_A,
                "status": "confirmed",
                "start_local": "2026-09-25T14:00:00+03:00",
                "laser_device_key": "candela",
                "laser_device_name": "Candela Gentle",
            }
        ],
        "packages": [
            {
                "package_id": PACKAGE,
                "name": "باكيدج ليزر إبط",
                "service_id": SERVICE_LASER,
                "laser_device_key": "candela",
                "remaining_sessions": 4,
                "total_sessions": 6,
                "status": "active",
            }
        ],
    }


def test_fresh_turn_keeps_all_service_identities_discoverable() -> None:
    context = build_semantic_context(_catalog())
    assert [row["ref"] for row in context.model_input["services"]] == ["S1", "S2"]


def test_fresh_turn_keeps_all_doctor_identities_discoverable() -> None:
    context = build_semantic_context(_catalog())
    assert [row["ref"] for row in context.model_input["doctors"]] == ["D1", "D2"]


def test_device_refs_are_ephemeral_and_canonical_server_side() -> None:
    context = build_semantic_context(_catalog())
    assert context.resolve("V1", expected_kind="device") == "prime"
    assert context.resolve("V2", expected_kind="device") == "candela"


def test_repeated_devices_are_normalized_once() -> None:
    catalog = _catalog()
    catalog["services"].append(
        {
            "id": "service-extra",
            "name": "ليزر رجل",
            "category": "laser",
            "laser_devices": [
                {"device_key": "prime", "device_name": "Prime Lase"},
                {"device_key": "candela", "device_name": "Candela Gentle"},
            ],
        }
    )
    context = build_semantic_context(catalog)
    assert len(context.model_input["devices"]) == 2
    assert "devices" not in context.model_input["services"][0]
    assert context.model_input["service_device_refs"] == {
        "S1": ["V1", "V2"],
        "S3": ["V1", "V2"],
    }


def test_verified_laser_pricing_continuation_focuses_service_and_device() -> None:
    context = with_safe_read_context(
        build_semantic_context(_catalog()),
        read_context={
            "operation_type": "pricing",
            "service_id": SERVICE_LASER,
            "device_key": "candela",
        },
    )
    focused = context.model_input["focused_context"]
    assert focused["services"][0]["ref"] == "S1"
    assert focused["devices"][0]["ref"] == "V2"


def test_new_unrelated_service_remains_discoverable_while_focused() -> None:
    context = with_safe_read_context(
        build_semantic_context(_catalog()),
        read_context={"operation_type": "pricing", "service_id": SERVICE_LASER},
    )
    assert {row["ref"] for row in context.model_input["services"]} == {"S1", "S2"}


def test_pricing_continuation_omits_unrelated_appointments() -> None:
    context = with_safe_read_context(
        build_semantic_context(_catalog()),
        read_context={"operation_type": "pricing", "service_id": SERVICE_LASER},
    )
    assert context.model_input["appointments"] == []


def test_pricing_continuation_omits_unrelated_packages() -> None:
    context = with_safe_read_context(
        build_semantic_context(_catalog()),
        read_context={"operation_type": "pricing", "service_id": SERVICE_LASER},
    )
    assert context.model_input["packages"] == []


def test_booking_flow_keeps_required_service_and_doctor_context() -> None:
    context = with_safe_task_context(
        build_semantic_context(_catalog()),
        active_task={
            "task_type": "booking",
            "status": "collecting",
            "constraints": {"service_id": SERVICE_LASER, "doctor_id": DOCTOR_A},
        },
    )
    focused = context.model_input["focused_context"]
    assert focused["services"][0]["ref"] == "S1"
    assert focused["doctors"][0]["ref"] == "D1"


def test_reschedule_context_retains_relevant_appointment_ref() -> None:
    context = with_safe_task_context(
        build_semantic_context(_catalog()),
        active_task={
            "task_type": "reschedule",
            "status": "collecting",
            "target": {"appointment_id": APPOINTMENT, "service_id": SERVICE_LASER},
            "replacement": {},
        },
    )
    assert [row["ref"] for row in context.model_input["appointments"]] == ["A1"]


def test_package_continuation_retains_relevant_package_ref() -> None:
    context = with_safe_read_context(
        build_semantic_context(_catalog()),
        read_context={
            "operation_type": "package_info",
            "service_id": SERVICE_LASER,
            "package_id": PACKAGE,
        },
    )
    assert [row["ref"] for row in context.model_input["packages"]] == ["P1"]


def test_stale_verified_reference_broadens_safely() -> None:
    context = with_safe_read_context(
        build_semantic_context(_catalog()),
        read_context={
            "operation_type": "pricing",
            "service_id": "missing-service-id",
        },
    )
    assert context.model_input["focused_context"] == {}
    assert [row["ref"] for row in context.model_input["appointments"]] == ["A1"]
    assert [row["ref"] for row in context.model_input["packages"]] == ["P1"]


def test_no_database_uuids_appear_in_model_input() -> None:
    context = build_semantic_context(_catalog())
    encoded = json.dumps(context.model_input, ensure_ascii=False)
    for canonical_id in (SERVICE_LASER, SERVICE_PRP, DOCTOR_A, DOCTOR_B, APPOINTMENT, PACKAGE):
        assert canonical_id not in encoded


def test_multi_operation_turn_has_complete_global_identity_indexes() -> None:
    context = with_safe_read_context(
        build_semantic_context(_catalog()),
        read_context={"operation_type": "pricing", "service_id": SERVICE_LASER},
    )
    assert {row["ref"] for row in context.model_input["services"]} == {"S1", "S2"}
    assert {row["ref"] for row in context.model_input["doctors"]} == {"D1", "D2"}
    assert {row["ref"] for row in context.model_input["devices"]} == {"V1", "V2"}


def test_reference_map_still_resolves_all_entity_kinds() -> None:
    context = build_semantic_context(_catalog())
    assert context.resolve("S1", expected_kind="service") == SERVICE_LASER
    assert context.resolve("D1", expected_kind="doctor") == DOCTOR_A
    assert context.resolve("A1", expected_kind="appointment") == APPOINTMENT
    assert context.resolve("P1", expected_kind="package") == PACKAGE
