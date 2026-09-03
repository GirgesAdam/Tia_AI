from uuid import uuid4

import pytest

from app.schemas.agent_knowledge import (
    AgentKnowledgeSnapshot,
    KnowledgeBranch,
    KnowledgeDoctor,
    KnowledgeEditAction,
    KnowledgeFieldChange,
    KnowledgeNamedLink,
    KnowledgeScheduleInterval,
    KnowledgeService,
)
from app.services.agent_knowledge import agent_knowledge_configuration_fingerprint
from app.services.agent_knowledge_edit import KnowledgeEditError, _validate_actions


def _snapshot() -> AgentKnowledgeSnapshot:
    branch_id, service_id, doctor_id, staff_id, workspace_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    return AgentKnowledgeSnapshot(
        workspace_id=workspace_id,
        workspace_name="Clinic",
        workspace_timezone="Africa/Cairo",
        branches=[KnowledgeBranch(id=branch_id, name="مدينة نصر", code="nasr-city", city="القاهرة", is_active=True, working_hours=[])],
        services=[KnowledgeService(id=service_id, name="فيلر", slug="filler", duration_minutes=45, price_minor=350000, currency="EGP", requires_medical_review=False, is_active=True)],
        doctors=[KnowledgeDoctor(id=doctor_id, staff_id=staff_id, name="أحمد محمود", first_name="أحمد", last_name="محمود", booking_enabled=True, is_active=True, branches=[KnowledgeNamedLink(id=branch_id, name="مدينة نصر", is_primary=True)], services=[KnowledgeNamedLink(id=service_id, name="فيلر")], schedules=[])],
        booking_settings=None,
        patients=[],
        appointments=[],
        patient_count=0,
        appointment_count=0,
    )


def test_configuration_fingerprint_ignores_operational_patient_and_appointment_lists() -> None:
    snapshot = _snapshot()
    first = agent_knowledge_configuration_fingerprint(snapshot)
    second = agent_knowledge_configuration_fingerprint(snapshot.model_copy(update={"patient_count": 500, "appointment_count": 999}))
    assert first == second


def test_service_edit_targets_exact_canonical_id() -> None:
    snapshot = _snapshot()
    action = KnowledgeEditAction(
        kind="update_service",
        entity_id=str(snapshot.services[0].id),
        changes=[KnowledgeFieldChange(field="duration_minutes", number_value=60)],
    )
    preview = _validate_actions(snapshot, [action])
    assert "فيلر" in preview[0]
    assert "duration_minutes = 60" in preview[0]


def test_unknown_entity_id_is_rejected_before_write() -> None:
    snapshot = _snapshot()
    action = KnowledgeEditAction(
        kind="update_service",
        entity_id=str(uuid4()),
        changes=[KnowledgeFieldChange(field="duration_minutes", number_value=60)],
    )
    with pytest.raises(KnowledgeEditError):
        _validate_actions(snapshot, [action])


def test_overlapping_schedule_is_rejected() -> None:
    snapshot = _snapshot()
    action = KnowledgeEditAction(
        kind="set_branch_hours",
        entity_id=str(snapshot.branches[0].id),
        schedule=[
            KnowledgeScheduleInterval(weekday=0, start_time="10:00", end_time="15:00"),
            KnowledgeScheduleInterval(weekday=0, start_time="14:00", end_time="20:00"),
        ],
    )
    with pytest.raises(KnowledgeEditError):
        _validate_actions(snapshot, [action])
