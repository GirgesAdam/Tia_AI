from types import SimpleNamespace

from app.services.automations import (
    _proactive_whatsapp_recipient,
    _real_proactive_whatsapp_connection,
)


def test_proactive_recipient_normalizes_egypt_mobile_to_provider_digits() -> None:
    patient = SimpleNamespace(phone_normalized="01012345678", phone="01012345678")
    assert _proactive_whatsapp_recipient(patient) == "201012345678"


def test_proactive_recipient_accepts_global_e164_and_rejects_ambiguous_local_phone() -> None:
    assert _proactive_whatsapp_recipient(
        SimpleNamespace(phone_normalized="+971501234567", phone="+971501234567")
    ) == "971501234567"
    assert _proactive_whatsapp_recipient(
        SimpleNamespace(phone_normalized="501234567", phone="501234567")
    ) is None


def test_proactive_connection_requires_one_real_sendable_whatsapp_runtime() -> None:
    good = SimpleNamespace(
        channel="whatsapp",
        status="active",
        external_account_id="phone-number-id",
        config_json={"runtime_kind": "real", "do_not_send": False},
    )
    assert _real_proactive_whatsapp_connection(good) is True

    for config in (
        {"runtime_kind": "real", "mock": True},
        {"runtime_kind": "real", "do_not_send": "true"},
        {"runtime_kind": "staging_mock"},
        {},
    ):
        candidate = SimpleNamespace(
            channel="whatsapp", status="active", external_account_id="phone-number-id", config_json=config
        )
        assert _real_proactive_whatsapp_connection(candidate) is False


def test_external_route_has_collision_and_ambiguity_guards() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "app/services/automations.py").read_text(encoding="utf-8")
    route = source.split("def _resolve_external_route(", 1)[1].split("def _followup_active_handoff(", 1)[0]
    assert "len(proactive_connections) != 1" in route
    assert "recipient_identity.patient_id != patient_id" in route
    assert '"source": "crm_patient_phone"' in route
    assert '"proactive_identity": True' in route
