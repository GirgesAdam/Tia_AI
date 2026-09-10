from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.capability_policy import CapabilityPolicyDecision
from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.tools.clinic_tools import AgentToolContext
from app.core.config import settings
from app.models.conversation import Conversation
from app.models.workspace import Workspace
from app.services.agent_chat import (
    _verified_cancellation_action,
    _with_current_patient_appointments,
)
from scripts.run_realistic_system_journeys import (
    HYDRA,
    UNDERARM,
    _actions,
    _find_slot,
    _new_patient,
    _seed_appointment,
)


def main() -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Workspace not found: tia")

        patient = _new_patient(db, workspace, 9912)
        laser_slot = _find_slot(db, workspace, UNDERARM, laser_device_key="prime_lase")
        laser = _seed_appointment(db, workspace, patient, laser_slot)
        hydra_slot = _find_slot(db, workspace, HYDRA, avoid=[(laser.start_at, laser.end_at)])
        hydra = _seed_appointment(db, workspace, patient, hydra_slot)

        now = datetime.now(UTC)
        conversation = Conversation(
            workspace_id=workspace.id,
            patient_id=patient.id,
            channel="whatsapp",
            status="open",
            owner_type="ai",
            unread_count=0,
            ownership_changed_at=now,
            started_at=now,
            last_message_at=now,
        )
        db.add(conversation)
        db.flush()

        catalog = _with_current_patient_appointments(
            db=db,
            workspace=workspace,
            patient=patient,
            clinic_catalog=build_clinic_catalog(db, workspace),
        )
        target = next(
            row
            for row in list(catalog.get("appointments") or [])
            if str(row.get("appointment_id") or row.get("id") or "") == str(hydra.id)
        )

        policy = CapabilityPolicyDecision(
            capabilities=frozenset({"appointment_cancellation"}),
            allowed_tools=frozenset({"get_customer_appointments", "cancel_appointment"}),
            write_capabilities=frozenset({"appointment_cancellation"}),
            requires_human=False,
            handoff_category="other",
            handoff_priority="normal",
            risk_flags=frozenset(),
        )
        decision = SimpleNamespace(
            entity_hints=SimpleNamespace(
                appointment_id=str(hydra.id),
                service_id=str(hydra.service_id),
                service_candidate_ids=[],
                doctor_id=str(hydra.doctor_id),
                doctor_candidate_ids=[],
                requested_date=None,
                requested_start_time=None,
            )
        )
        tool_context = AgentToolContext(
            db=db,
            workspace=workspace,
            patient=patient,
            conversation=conversation,
            run_id=uuid4(),
        )

        before = {"laser": laser.status, "hydra": hydra.status}
        result = _verified_cancellation_action(
            tool_context=tool_context,
            policy=policy,
            decision=decision,
            clinic_catalog=catalog,
        )
        db.flush()
        db.refresh(laser)
        db.refresh(hydra)
        after = {"laser": laser.status, "hydra": hydra.status}

        print(
            json.dumps(
                {
                    "target": target,
                    "helper_result": result,
                    "before": before,
                    "after": after,
                    "actions": _actions(db, workspace, patient),
                    "openai_calls": 0,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


if __name__ == "__main__":
    main()
