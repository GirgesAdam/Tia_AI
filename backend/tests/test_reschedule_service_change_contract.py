from pathlib import Path

from app.services.appointment_operations import service_change_requires_human


def test_unpaid_standard_booking_can_change_service() -> None:
    assert service_change_requires_human(
        payment_status="unknown",
        amount_paid_minor=None,
        billing_context="standard",
        patient_package_id=None,
        package_external_id=None,
        has_payment_allocation=False,
    ) is False
    assert service_change_requires_human(
        payment_status="unpaid",
        amount_paid_minor=0,
        billing_context="standard",
        patient_package_id=None,
        package_external_id=None,
        has_payment_allocation=False,
    ) is False


def test_paid_or_package_booking_service_change_requires_human() -> None:
    base = dict(
        payment_status="unknown",
        amount_paid_minor=None,
        billing_context="standard",
        patient_package_id=None,
        package_external_id=None,
        has_payment_allocation=False,
    )
    cases = [
        {"payment_status": "paid"},
        {"payment_status": "partial"},
        {"amount_paid_minor": 100},
        {"billing_context": "package_prepaid"},
        {"package_external_id": "PKG-1"},
        {"has_payment_allocation": True},
    ]
    for override in cases:
        payload = {**base, **override}
        assert service_change_requires_human(**payload) is True


def test_reschedule_service_id_flows_from_verified_slot_to_native_operation() -> None:
    backend = Path(__file__).resolve().parent.parent
    semantic = (backend / "app/agents/semantic_actions.py").read_text(encoding="utf-8")
    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    adapter = (backend / "app/integrations/clinic/tia_database.py").read_text(encoding="utf-8")
    operations = (backend / "app/services/appointment_operations.py").read_text(encoding="utf-8")

    assert '"service_id": str(slot.get("service_id") or "")' in semantic
    assert 'service_id: str = ""' in tools
    assert 'service_id=service_id or None' in tools
    assert 'service_id=new_service_id' in adapter
    assert 'service_id=new_service_id' in operations
    assert 'AppointmentServiceChangeRequiresHuman' in operations


def test_reschedule_discovery_keeps_current_appointment_separate_from_target_service() -> None:
    backend = Path(__file__).resolve().parent.parent
    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    chat = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert "if service_id and not appointment_id:" in tools
    assert "target_service_id = service_id or current.service_id" in tools
    assert "service_id=target_service_id" in tools
    assert 'snapshot_current = flow.option_snapshot.get("current_appointment")' in chat


def test_financially_sensitive_service_change_escalates_instead_of_faking_failure() -> None:
    backend = Path(__file__).resolve().parent.parent
    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    chat = (backend / "app/services/agent_chat.py").read_text(encoding="utf-8")

    assert '"requires_human": True' in tools
    assert 'tool_name="escalate_to_human"' in chat
    assert "reschedule_service_change_requires_human" in chat
