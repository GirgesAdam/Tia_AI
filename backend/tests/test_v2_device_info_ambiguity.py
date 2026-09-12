from datetime import UTC, datetime

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_contract import (
    EntityReference,
    TiaTurnUnderstanding,
    TurnEntities,
    TurnOperation,
)
from app.services.agent_v2.planner import PlannerContext, plan_turn

NOW = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)


def _context() -> PlannerContext:
    semantic = build_semantic_context(
        {
            "services": [
                {
                    "id": "service-underarm",
                    "name": "ليزر إبط",
                    "requires_laser_device": True,
                    "laser_devices": [
                        {"device_key": "candela", "device_name": "Candela Gentle"},
                        {"device_key": "prime", "device_name": "Prime Lase"},
                    ],
                }
            ],
            "doctors": [],
        }
    )
    return PlannerContext(semantic_context=semantic, active_task=None, now=NOW)


def _ambiguous_device_entities() -> TurnEntities:
    return TurnEntities(device=EntityReference(candidate_refs=["V1", "V2"]))


def test_clinic_info_can_compare_multiple_devices_without_forcing_selection() -> None:
    turn = TiaTurnUnderstanding(
        operations=[TurnOperation(type="clinic_info", entities=_ambiguous_device_entities())],
        safety_signals=[],
    )

    step = plan_turn(turn, _context()).steps[0]

    assert step.disposition == "read"
    assert [read.kind for read in step.reads] == ["clinic_info"]
    assert step.clarification_field is None


def test_device_sensitive_doctor_lookup_still_requires_one_device() -> None:
    turn = TiaTurnUnderstanding(
        operations=[TurnOperation(type="doctor_info", entities=_ambiguous_device_entities())],
        safety_signals=[],
    )

    step = plan_turn(turn, _context()).steps[0]

    assert step.disposition == "clarify"
    assert step.clarification_field == "device"
