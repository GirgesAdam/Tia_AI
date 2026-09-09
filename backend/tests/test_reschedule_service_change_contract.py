from pathlib import Path


def _source(relative_path: str) -> str:
    backend = Path(__file__).resolve().parent.parent
    return (backend / relative_path).read_text(encoding="utf-8")


def test_reschedule_service_id_flows_from_verified_slot_to_native_operation() -> None:
    semantic = _source("app/agents/semantic_actions.py")
    tools = _source("app/agents/tools/clinic_tools.py")
    adapter = _source("app/integrations/clinic/tia_database.py")
    operations = _source("app/services/appointment_operations.py")

    assert '"service_id": str(slot.get("service_id") or "")' in semantic
    assert 'service_id: str = ""' in tools
    assert 'service_id=service_id or None' in tools
    assert "service_id=new_service_id" in adapter
    assert "service_id=new_service_id" in operations


def test_reschedule_discovery_keeps_current_appointment_separate_from_target_service() -> None:
    tools = _source("app/agents/tools/clinic_tools.py")
    chat = _source("app/services/agent_chat.py")

    assert "if service_id and not appointment_id:" in tools
    assert "target_service_id = service_id or current.service_id" in tools
    assert "service_id=target_service_id" in tools
    assert 'snapshot_current = flow.option_snapshot.get("current_appointment")' in chat


def test_agent_service_change_does_not_handoff_only_because_money_or_package_exists() -> None:
    operations = _source("app/services/appointment_operations.py")
    adapter = _source("app/integrations/clinic/tia_database.py")

    assert "AppointmentServiceChangeRequiresHuman" not in operations
    assert "service_change_requires_human" not in operations
    assert "AppointmentServiceChangeRequiresHuman" not in adapter
    assert "reallocate_appointment_payments_on_reschedule" in operations
    assert "refresh_appointment_payment_snapshots" in operations


def test_reschedule_preserves_only_compatible_package_entitlement() -> None:
    operations = _source("app/services/appointment_operations.py")
    packages = _source("app/services/patient_packages.py")

    assert "_package_matches_replacement" in operations
    assert "package.service_id == replacement.service_id" in operations
    assert "package.laser_device_key == replacement.laser_device_key" in operations
    assert 'reason="appointment_service_or_device_changed"' in operations
    assert "replacement.patient_package_id = None" in operations
    assert "transfer_package_usage(" in operations
    assert "package.laser_device_key != to_appointment.laser_device_key" in packages


def test_laser_device_is_part_of_agent_reschedule_adapter_contract() -> None:
    contract = _source("app/integrations/clinic/base.py")
    laser_adapter = _source("app/integrations/clinic/tia_database_laser.py")
    operations = _source("app/services/appointment_operations.py")

    reschedule_request = contract[contract.index("class RescheduleAppointmentRequest"):]
    assert "laser_device_key: str | None = None" in reschedule_request
    assert "request.laser_device_key" in laser_adapter
    assert "laser_device_key=laser_device_key" in operations
    assert "laser_device_key=slot.laser_device_key" in operations
