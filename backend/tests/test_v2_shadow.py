from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.agents.v2.turn_contract import TiaTurnUnderstanding, TurnEntities, TurnOperation
from app.services.agent_v2 import shadow
from app.services.agent_v2.planner import (
    PlanStep,
    ReadRequest,
    TurnPlan,
    VerificationFacts,
    WriteIntent,
)
from app.services.agent_v2.read_executor import ReadExecutionBundle, ReadResult

NOW = datetime(2026, 9, 11, 16, 0, tzinfo=UTC)


def _turn(operation_type: str) -> TiaTurnUnderstanding:
    return TiaTurnUnderstanding(
        operations=[
            TurnOperation(
                type=operation_type,
                entities=TurnEntities(),
                selection=None,
                package_usage="unspecified",
            )
        ],
        safety_signals=[],
    )


def _workspace():
    return SimpleNamespace(id="workspace-1", name="Tia Clinic", timezone="Africa/Cairo")


def _patient():
    return SimpleNamespace(id="patient-1")


def test_shadow_read_only_turn_can_render_one_v2_reply(monkeypatch) -> None:
    turn = _turn("pricing")
    plan = TurnPlan(
        steps=[
            PlanStep(
                operation_index=0,
                operation_type="pricing",
                disposition="read",
                reads=[ReadRequest(kind="service_catalog", parameters={})],
                response_goal="answer_price",
            )
        ]
    )
    bundle = ReadExecutionBundle(
        results=[
            ReadResult(
                kind="service_catalog",
                ok=True,
                payload={
                    "service": {
                        "id": "internal-service-id",
                        "name": "ليزر إبط",
                        "price_minor": 50_000,
                        "currency": "EGP",
                    }
                },
            )
        ]
    )

    monkeypatch.setattr(shadow, "build_patient_semantic_catalog_v2", lambda **_kwargs: {})
    monkeypatch.setattr(shadow, "interpret_customer_turn_v2", lambda **_kwargs: turn)
    monkeypatch.setattr(shadow, "plan_turn", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(shadow, "execute_step_reads", lambda *_args, **_kwargs: bundle)
    monkeypatch.setattr(
        shadow,
        "compose_v2_customer_reply",
        lambda **kwargs: (
            "ليزر الإبط سعره 500 جنيه.",
            "openai:test-model",
        ),
    )

    result = shadow.run_v2_shadow_turn(
        db=object(),
        workspace=_workspace(),
        patient=_patient(),
        history=[HumanMessage(content="ليزر الإبط بكام؟")],
        local_now=NOW,
    )

    assert result.reply == "ليزر الإبط سعره 500 جنيه."
    assert result.responder_model == "openai:test-model"
    assert result.reply_skipped_reason is None
    assert len(result.outcomes) == 1
    assert result.outcomes[0].response_goal == "answer_price"


def test_shadow_write_ready_turn_never_calls_responder_or_executes_write(monkeypatch) -> None:
    turn = _turn("book")
    plan = TurnPlan(
        steps=[
            PlanStep(
                operation_index=0,
                operation_type="book",
                disposition="read",
                reads=[ReadRequest(kind="availability", parameters={})],
                write_intent=WriteIntent(
                    kind="booking",
                    authorized=True,
                    parameters={},
                    requires_verification=True,
                ),
                response_goal="present_availability",
                facts={"exact_time_requested": True},
            )
        ]
    )
    bundle = ReadExecutionBundle(
        results=[ReadResult(kind="availability", ok=True, payload={"slots": []})],
        verification=VerificationFacts(
            exact_slot_match_count=1,
            verified_parameters={"start_at": "2026-09-12T19:00:00+03:00"},
        ),
    )

    monkeypatch.setattr(shadow, "build_patient_semantic_catalog_v2", lambda **_kwargs: {})
    monkeypatch.setattr(shadow, "interpret_customer_turn_v2", lambda **_kwargs: turn)
    monkeypatch.setattr(shadow, "plan_turn", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(shadow, "execute_step_reads", lambda *_args, **_kwargs: bundle)

    def _unexpected_responder(**_kwargs):
        raise AssertionError("Responder must not render a success reply for an unexecuted shadow write.")

    monkeypatch.setattr(shadow, "compose_v2_customer_reply", _unexpected_responder)

    result = shadow.run_v2_shadow_turn(
        db=object(),
        workspace=_workspace(),
        patient=_patient(),
        history=[HumanMessage(content="احجزلي بكرة الساعة 7")],
        local_now=NOW,
    )

    assert result.reply is None
    assert result.reply_skipped_reason == "write_execution_required"
    assert result.outcomes == []
    assert result.step_traces[0].disposition_after == "write_ready"
    assert result.step_traces[0].write_preview is not None
    assert result.step_traces[0].write_preview["kind"] == "booking"


def test_shadow_module_contains_no_database_mutation_or_write_adapter_calls() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/agent_v2/shadow.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "db.commit",
        "db.flush",
        "db.add",
        "create_appointment",
        "cancel_appointment(",
        "reschedule_appointment",
        "confirm_appointment(",
        "purchase_package_offer(",
        "marketing_consent",
        "create_follow_up",
    )
    for token in forbidden:
        assert token not in source
