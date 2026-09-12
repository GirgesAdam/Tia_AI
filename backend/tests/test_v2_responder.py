from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.llm_runtime import LLMProviderError
from app.agents.v2 import responder
from app.agents.v2.responder import _build_responder_messages, compose_v2_customer_reply
from app.services.agent_v2.outcome import TurnOutcome

NOW = datetime(2026, 9, 11, 16, 0, tzinfo=UTC)
INTERNAL_UUID = "123e4567-e89b-12d3-a456-426614174000"


def _price_outcome() -> TurnOutcome:
    return TurnOutcome(
        status="answered",
        response_goal="answer_price",
        facts={
            "service_catalog": {
                "service": {
                    "id": INTERNAL_UUID,
                    "service_id": INTERNAL_UUID,
                    "name": "ليزر إبط",
                    "price_minor": 50_000,
                    "currency": "EGP",
                }
            }
        },
    )


def _doctor_outcome() -> TurnOutcome:
    return TurnOutcome(
        status="answered",
        response_goal="answer_doctor",
        facts={
            "doctors": {
                "doctors": [
                    {"name": "د. مريم"},
                    {"name": "د. سارة"},
                    {"name": "د. نور"},
                ]
            }
        },
    )


def test_responder_preserves_native_dialogue_roles_and_keeps_latest_customer_last() -> None:
    history = [
        HumanMessage(content="عايزة ليزر إبط"),
        AIMessage(content="تحبي تعرفي السعر ولا المواعيد؟"),
        HumanMessage(content="السعر كام؟"),
    ]

    messages = _build_responder_messages(
        clinic_name="Tia Clinic",
        timezone_name="Africa/Cairo",
        local_now=NOW,
        history=history,
        outcomes=[_price_outcome()],
    )

    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    assert isinstance(messages[3], SystemMessage)
    assert isinstance(messages[4], HumanMessage)
    assert messages[4].content == "السعر كام؟"


def test_responder_payload_removes_internal_ids_and_formats_money_before_llm() -> None:
    messages = _build_responder_messages(
        clinic_name="Tia Clinic",
        timezone_name="Africa/Cairo",
        local_now=NOW,
        history=[HumanMessage(content="ليزر الإبط بكام؟")],
        outcomes=[_price_outcome()],
    )
    payload = str(messages[-2].content)

    assert INTERNAL_UUID not in payload
    assert "service_id" not in payload
    assert "500.00 EGP" in payload
    assert "ليزر إبط" in payload


def test_compound_outcomes_are_given_to_one_responder_call() -> None:
    outcomes = [
        _price_outcome(),
        TurnOutcome(
            status="answered",
            response_goal="present_availability",
            facts={
                "availability": {
                    "service_name": "ليزر إبط",
                    "checked_dates": ["2026-09-12"],
                    "availability_windows": [
                        {
                            "doctor_name": "د. مريم",
                            "start_time_24h": "18:00",
                            "end_time_24h": "20:00",
                        }
                    ],
                }
            },
        ),
    ]
    messages = _build_responder_messages(
        clinic_name="Tia Clinic",
        timezone_name="Africa/Cairo",
        local_now=NOW,
        history=[HumanMessage(content="الإبط بكام وإيه المتاح بكرة؟")],
        outcomes=outcomes,
    )
    payload = str(messages[-2].content)

    assert '"response_goal":"answer_price"' in payload
    assert '"response_goal":"present_availability"' in payload
    assert len([message for message in messages if isinstance(message, HumanMessage)]) == 1


def test_compose_v2_customer_reply_returns_one_model_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(responder, "build_realtime_composer_model", lambda: object())
    monkeypatch.setattr(
        responder,
        "invoke_with_model_chain",
        lambda **_kwargs: SimpleNamespace(
            value=AIMessage(content="ليزر الإبط سعره 500 جنيه، والمتاح بكرة من 6 لـ8 مساءً مع د. مريم."),
            model_name="test-model",
        ),
    )

    text, model = compose_v2_customer_reply(
        clinic_name="Tia Clinic",
        timezone_name="Africa/Cairo",
        local_now=NOW,
        history=[HumanMessage(content="الإبط بكام؟")],
        outcomes=[_price_outcome()],
    )

    assert text == "ليزر الإبط سعره 500 جنيه، والمتاح بكرة من 6 لـ8 مساءً مع د. مريم."
    assert model == "openai:test-model"


def test_pure_doctor_list_is_complete_once_and_skips_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_built():
        raise AssertionError("pure doctor discovery should not build the responder model")

    monkeypatch.setattr(responder, "build_realtime_composer_model", fail_if_built)

    text, model = compose_v2_customer_reply(
        clinic_name="Tia Clinic",
        timezone_name="Africa/Cairo",
        local_now=NOW,
        history=[HumanMessage(content="مين الدكاترة اللي بيعملوا ليزر الإبط؟")],
        outcomes=[_doctor_outcome()],
    )

    assert model == "deterministic:doctor-list"
    assert text.count("د. مريم") == 1
    assert text.count("د. سارة") == 1
    assert text.count("د. نور") == 1


def test_doctor_list_does_not_bypass_model_for_compound_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(responder, "build_realtime_composer_model", lambda: object())
    monkeypatch.setattr(
        responder,
        "invoke_with_model_chain",
        lambda **_kwargs: SimpleNamespace(
            value=AIMessage(
                content="الدكاترة د. مريم ود. سارة ود. نور، وسعر ليزر الإبط 500 جنيه."
            ),
            model_name="test-model",
        ),
    )

    text, model = compose_v2_customer_reply(
        clinic_name="Tia Clinic",
        timezone_name="Africa/Cairo",
        local_now=NOW,
        history=[HumanMessage(content="مين الدكاترة والسعر كام؟")],
        outcomes=[_doctor_outcome(), _price_outcome()],
    )

    assert model == "openai:test-model"
    assert "500 جنيه" in text
    assert text.count("د. مريم") == 1
    assert text.count("د. سارة") == 1
    assert text.count("د. نور") == 1


def test_empty_responder_output_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(responder, "build_realtime_composer_model", lambda: object())
    monkeypatch.setattr(
        responder,
        "invoke_with_model_chain",
        lambda **_kwargs: SimpleNamespace(value=AIMessage(content="   "), model_name="test-model"),
    )

    with pytest.raises(LLMProviderError):
        compose_v2_customer_reply(
            clinic_name="Tia Clinic",
            timezone_name="Africa/Cairo",
            local_now=NOW,
            history=[HumanMessage(content="السعر كام؟")],
            outcomes=[_price_outcome()],
        )
