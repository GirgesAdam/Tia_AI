from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.schemas.crm import (
    PatientCRMStats,
    PatientProfileRead,
    PatientRead,
    PatientTimelineEvent,
    PatientTimelineMessage,
)
from app.services.patient_timeline import merge_timeline_events


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_patient_profile_schema_keeps_canonical_patient_and_operational_stats() -> None:
    now = datetime(2026, 8, 24, 21, 0, tzinfo=UTC)
    patient_id = uuid4()
    workspace_id = uuid4()
    conversation_id = uuid4()
    message_id = uuid4()

    profile = PatientProfileRead(
        patient=PatientRead(
            id=patient_id,
            workspace_id=workspace_id,
            first_name="Nour",
            last_name="Ali",
            phone="+201000000000",
            gender=None,
            birth_date=None,
            preferred_language="ar",
            preferred_branch_id=None,
            source="whatsapp",
            source_detail=None,
            status="active",
            marketing_consent=False,
            marketing_consent_at=None,
            last_contact_at=now,
            created_at=now - timedelta(days=30),
            updated_at=now,
        ),
        stats=PatientCRMStats(
            total_appointments=4,
            completed_appointments=2,
            no_show_appointments=1,
            upcoming_appointments=1,
            total_conversations=3,
            open_conversations=1,
            active_handoffs=0,
            active_leads=1,
            next_appointment_at=now + timedelta(days=2),
            last_appointment_at=now - timedelta(days=5),
        ),
        tags=[],
        notes=[],
        timeline=[
            PatientTimelineEvent(
                id=f"message:{message_id}",
                kind="message",
                occurred_at=now,
                actor_type="patient",
                message=PatientTimelineMessage(
                    id=message_id,
                    conversation_id=conversation_id,
                    sender_type="patient",
                    direction="inbound",
                    message_type="text",
                    content="عايزة أأكد المعاد",
                    delivery_status="received",
                    channel="whatsapp",
                ),
            )
        ],
        latest_conversation_id=conversation_id,
    )

    assert profile.patient.id == patient_id
    assert profile.stats.upcoming_appointments == 1
    assert profile.timeline[0].message and profile.timeline[0].message.channel == "whatsapp"
    assert profile.latest_conversation_id == conversation_id


def test_timeline_merge_is_globally_descending_and_bounded() -> None:
    base = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)
    events = [
        PatientTimelineEvent(id="a", kind="patient_created", occurred_at=base),
        PatientTimelineEvent(id="b", kind="patient_created", occurred_at=base + timedelta(minutes=2)),
        PatientTimelineEvent(id="c", kind="patient_created", occurred_at=base + timedelta(minutes=1)),
    ]

    merged = merge_timeline_events([[events[0], events[1]], [events[2]]], limit=2)

    assert [event.id for event in merged] == ["b", "c"]


def test_patient_profile_read_model_uses_existing_canonical_tables_without_llm() -> None:
    service = (_root() / "backend/app/services/patient_timeline.py").read_text(encoding="utf-8")

    for model in (
        "Appointment",
        "AppointmentStatusHistory",
        "Conversation",
        "Message",
        "HandoffRequest",
        "HandoffEvent",
        "PatientNote",
        "PatientTag",
        "Lead",
    ):
        assert model in service

    lowered = service.lower()
    assert "llm" not in lowered
    assert "keyword" not in lowered
    assert "patienttimelineevent" in lowered
    assert "workspace_id == workspace_id" in service
    assert "patient_id == patient.id" in service


def test_crm_exposes_single_patient_profile_endpoint_with_bounded_timeline() -> None:
    route = (_root() / "backend/app/api/routes/crm.py").read_text(encoding="utf-8")
    start = route.index('@router.get("/patients/{patient_id}/profile"')
    end = route.index('@router.patch("/patients/{patient_id}"', start)
    block = route[start:end]

    assert "response_model=PatientProfileRead" in block
    assert "timeline_limit: Annotated[int, Query(ge=1, le=100)] = 50" in block
    assert "get_patient_or_404" in block
    assert "workspace_id=access.workspace.id" in block
    assert "build_patient_profile" in block


def test_patient_ui_links_list_to_profile_and_writes_notes_through_existing_api() -> None:
    list_page = (_root() / "frontend/src/app/(dashboard)/patients/page.tsx").read_text(encoding="utf-8")
    profile_page = (_root() / "frontend/src/app/(dashboard)/patients/[patientId]/page.tsx").read_text(
        encoding="utf-8"
    )
    actions = (_root() / "frontend/src/app/(dashboard)/patients/actions.ts").read_text(encoding="utf-8")
    inbox_detail = (_root() / "frontend/src/app/(dashboard)/inbox/[conversationId]/page.tsx").read_text(encoding="utf-8")

    assert "`/patients/${patient.id}`" in list_page
    assert "/profile?timeline_limit=75" in profile_page
    assert "profile.timeline.map" in profile_page
    assert "profile.latest_conversation_id" in profile_page
    assert "addPatientNote" in profile_page
    assert "/notes" in actions
    assert 'method: "POST"' in actions
    assert "`/patients/${conversation.patient.id}`" in inbox_detail
    assert "llm" not in profile_page.lower()



def test_patient_profile_latency_path_reuses_notes_and_batches_kpis() -> None:
    service = (_root() / "backend/app/services/patient_timeline.py").read_text(encoding="utf-8")
    stats_start = service.index("def _build_stats_and_latest_conversation(")
    notes_start = service.index("def _load_note_rows(", stats_start)
    stats_block = service[stats_start:notes_start]
    profile_start = service.index("def build_patient_profile(")
    profile_block = service[profile_start:]

    assert stats_block.count("db.execute(") == 1
    assert stats_block.count("scalar_subquery()") >= 3
    assert profile_block.count("_load_note_rows(") == 1
    assert "_build_note_events(note_rows[:per_source_limit])" in profile_block
    assert "db.scalar(" not in profile_block
