from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.agents.v2.turn_contract import DateConstraint
from app.core.config import settings
from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.conversation import Conversation
from app.models.doctor import Doctor
from app.models.message import Message
from app.models.patient import Patient
from app.models.patient_package import PatientPackage
from app.models.payment_transaction import PaymentTransaction
from app.models.service import Service
from app.models.staff import Staff
from app.models.workspace import Workspace
from app.services.agent_v2 import live_chat
from app.services.agent_v2.orchestrator import V2TurnInterpretationStructuredOutputError
from app.services.agent_v2.state import BookingTaskState, CustomerConstraints, WriteAuthorization
from app.services.agent_v2.state_persistence import load_active_task, save_active_task


@contextmanager
def _db_session():
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


def _count(db: Session, model, workspace_id):
    return db.scalar(select(func.count()).select_from(model).where(model.workspace_id == workspace_id))


def test_structured_failure_is_business_state_neutral_and_preserves_context(
    monkeypatch,
) -> None:
    with _db_session() as db:
        suffix = uuid4().hex[:10]
        now = datetime.now(UTC)
        workspace = Workspace(
            name=f"SO containment {suffix}",
            slug=f"so-containment-{suffix}",
            timezone="Africa/Cairo",
            is_active=True,
            is_demo=True,
        )
        db.add(workspace)
        db.flush()
        branch = Branch(
            workspace_id=workspace.id,
            name="Main",
            code=f"SO-{suffix}",
            city="Cairo",
            country_code="EG",
            timezone="Africa/Cairo",
            is_active=True,
        )
        staff = Staff(
            workspace_id=workspace.id,
            first_name="SO",
            last_name="Doctor",
            is_active=True,
        )
        service = Service(
            workspace_id=workspace.id,
            name=f"SO Service {suffix}",
            slug=f"so-service-{suffix}",
            operational_category="dermatology",
            duration_minutes=45,
            price_minor=200_000,
            currency="EGP",
            is_active=True,
        )
        patient = Patient(
            workspace_id=workspace.id,
            first_name="SO",
            preferred_language="ar",
            source="other",
            status="active",
        )
        db.add_all([branch, staff, service, patient])
        db.flush()
        workspace.primary_branch_id = branch.id
        doctor = Doctor(
            workspace_id=workspace.id,
            staff_id=staff.id,
            doctor_type="regular",
            booking_enabled=True,
            is_active=True,
        )
        db.add(doctor)
        db.flush()
        appointment_start = now + timedelta(days=1)
        appointment = Appointment(
            workspace_id=workspace.id,
            patient_id=patient.id,
            branch_id=branch.id,
            doctor_id=doctor.id,
            doctor_assignment_known=True,
            service_id=service.id,
            status="confirmed",
            source="ai",
            start_at=appointment_start,
            end_at=appointment_start + timedelta(minutes=45),
            busy_start_at=appointment_start,
            busy_end_at=appointment_start + timedelta(minutes=45),
            duration_minutes=45,
            price_minor=200_000,
            discount_minor=0,
            currency="EGP",
            payment_status="unpaid",
            payment_method="unknown",
            billing_context="standard",
        )
        conversation = Conversation(
            workspace_id=workspace.id,
            patient_id=patient.id,
            channel="web",
            status="open",
            owner_type="ai",
            started_at=now - timedelta(minutes=10),
            last_message_at=now - timedelta(minutes=1),
        )
        db.add_all([appointment, conversation])
        db.flush()

        active_task = BookingTaskState(
            write_authorization=WriteAuthorization(
                operation="booking",
                authorized=True,
                source_turn_id="seed",
                granted_at=now,
            ),
            constraints=CustomerConstraints(
                service_id=str(service.id),
                date=DateConstraint(
                    mode="exact",
                    start_date=(now + timedelta(days=2)).date().isoformat(),
                ),
            ),
        )
        before_task = save_active_task(
            db,
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            patient_id=patient.id,
            active_task=active_task,
            run_id=uuid4(),
        )

        read_context = {
            "operation_type": "availability",
            "service_ref": "S1",
            "package_inquiry_context": {"owned": True},
        }
        availability_context = {
            "last_selected_option_ref": "slot-2",
            "availability_reference_options": [
                {"option_ref": "slot-1", "start_local": "2026-10-11T16:00:00+03:00"},
                {"option_ref": "slot-2", "start_local": "2026-10-11T16:45:00+03:00"},
            ],
        }
        pending_choice = {
            "kind": "appointment",
            "options": [{"ref": "A1"}, {"ref": "A2"}],
        }
        prior = Message(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            sender_type="ai",
            direction="outbound",
            created_at=now - timedelta(minutes=2),
            message_type="text",
            content="اختاري من المواعيد المتاحة.",
            delivery_status="sent",
            metadata_json={
                "runtime": "v2",
                "v2_read_context": read_context,
                "v2_availability_reference_context": availability_context,
                "v2_pending_choice": pending_choice,
            },
        )
        inbound = Message(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            sender_type="patient",
            direction="inbound",
            created_at=now - timedelta(minutes=1),
            message_type="text",
            content="التاني عامل الساعة كام؟",
            delivery_status="received",
            metadata_json={},
        )
        db.add_all([prior, inbound])
        db.flush()

        before = {
            "appointments": _count(db, Appointment, workspace.id),
            "packages": _count(db, PatientPackage, workspace.id),
            "payments": _count(db, PaymentTransaction, workspace.id),
            "appointment_status": appointment.status,
        }

        monkeypatch.setattr(live_chat, "get_active_handoff", lambda *a, **k: None)
        monkeypatch.setattr(live_chat, "agent_can_reply", lambda *_a, **_k: True)
        monkeypatch.setattr(
            live_chat,
            "lock_conversation_ownership",
            lambda *a, **k: conversation,
        )
        monkeypatch.setattr(live_chat, "get_clinic_adapter", lambda **_k: object())
        monkeypatch.setattr(
            live_chat,
            "orchestrate_v2_turn",
            lambda **_k: (_ for _ in ()).throw(
                V2TurnInterpretationStructuredOutputError("structured interpretation exhausted")
            ),
        )
        monkeypatch.setattr(
            live_chat,
            "execute_write_ready_step",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("business write must not run")),
        )

        result = live_chat._run_v2_after_inbound(
            db=db,
            workspace=workspace,
            patient=patient,
            conversation=conversation,
            inbound=inbound,
            run_id=uuid4(),
            outbound_delivery_status="sent",
            source="test",
        )
        db.flush()
        db.refresh(appointment)

        after = {
            "appointments": _count(db, Appointment, workspace.id),
            "packages": _count(db, PatientPackage, workspace.id),
            "payments": _count(db, PaymentTransaction, workspace.id),
            "appointment_status": appointment.status,
        }
        after_task = load_active_task(
            db,
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            patient_id=patient.id,
            run_id=uuid4(),
        )

        assert result.reply is not None and result.reply.strip()
        assert result.model == "deterministic:structured-output-clarification"
        assert after == before
        assert after_task is not None
        assert after_task.active_task == before_task.active_task
        assert after_task.flow_id == before_task.flow_id
        assert after_task.flow_version == before_task.flow_version

        clarification = db.scalar(
            select(Message).where(
                Message.workspace_id == workspace.id,
                Message.in_reply_to_message_id == inbound.id,
                Message.sender_type == "ai",
            )
        )
        assert clarification is not None
        assert clarification.metadata_json["v2_read_context"] == read_context
        assert clarification.metadata_json["v2_availability_reference_context"] == availability_context
        assert clarification.metadata_json["v2_pending_choice"] == pending_choice

        next_inbound = Message(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            sender_type="patient",
            direction="inbound",
            created_at=clarification.created_at + timedelta(seconds=1),
            message_type="text",
            content="قصدي الاختيار التاني.",
            delivery_status="received",
            metadata_json={},
        )
        db.add(next_inbound)
        db.flush()
        assert live_chat._recent_verified_read_context(
            db,
            conversation=conversation,
            inbound=next_inbound,
        ) == read_context
        assert live_chat._recent_availability_reference_context(
            db,
            conversation=conversation,
            inbound=next_inbound,
        ) == availability_context
        assert live_chat._recent_pending_choice_context(
            db,
            conversation=conversation,
            inbound=next_inbound,
        ) == pending_choice
