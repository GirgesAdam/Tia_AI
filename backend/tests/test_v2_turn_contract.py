from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.structured_output import canonicalize_provider_json_schema
from app.agents.v2.turn_contract import (
    DateConstraint,
    Selection,
    TiaTurnUnderstanding,
    TimeConstraint,
    TurnEntities,
    TurnOperation,
)


def test_v2_turn_schema_is_strict_provider_compatible() -> None:
    schema = TiaTurnUnderstanding.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])

    provider = canonicalize_provider_json_schema(schema)
    assert "$defs" not in provider
    assert "$ref" not in str(provider)


def test_v2_contract_supports_compound_operations_without_capability_fields() -> None:
    turn = TiaTurnUnderstanding(
        operations=[
            TurnOperation(
                type="pricing",
                entities=TurnEntities(),
                selection=None,
                package_usage="unspecified",
            ),
            TurnOperation(
                type="availability",
                entities=TurnEntities(
                    date=DateConstraint(
                        mode="exact",
                        start_date="2026-09-12",
                        end_date=None,
                    )
                ),
                selection=None,
                package_usage="unspecified",
            ),
        ],
        safety_signals=[],
    )
    payload = turn.model_dump()
    assert [item["type"] for item in payload["operations"]] == ["pricing", "availability"]
    forbidden = {
        "domains",
        "capabilities",
        "flow_signal",
        "clear_entity_fields",
        "missing_information",
        "confidence",
        "reason",
        "recommended_handoff_category",
        "recommended_handoff_priority",
    }
    assert forbidden.isdisjoint(payload)


def test_v2_date_time_and_selection_shapes_fail_closed() -> None:
    with pytest.raises(ValidationError):
        DateConstraint(mode="range", start_date="2026-09-12", end_date=None)

    with pytest.raises(ValidationError):
        TimeConstraint(mode="range", start_time="20:00", end_time="18:00")

    with pytest.raises(ValidationError):
        Selection(kind="index", index=0, time=None, ref=None)
