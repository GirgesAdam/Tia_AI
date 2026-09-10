from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.services.agent_chat as agent_chat_module
from app.core.config import settings
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.workspace import Workspace
from app.schemas.agent import AgentChatRequest
from scripts.run_realistic_system_journeys import (
    HYDRA,
    UNDERARM,
    TokenMeter,
    _actions,
    _find_slot,
    _new_patient,
    _seed_appointment,
)


def _small(decision) -> dict[str, object]:
    data = decision.model_dump(mode="json")
    hints = data.get("entity_hints") or {}
    return {
        "capabilities": data.get("capabilities"),
        "action": data.get("action"),
        "selection_index": data.get("selection_index"),
        "missing_information": data.get("missing_information"),
        "confidence": data.get("confidence"),
        "reason": data.get("reason"),
        "entity_hints": {
            key: hints.get(key)
            for key in (
                "service_query",
                "service_id",
                "service_candidate_ids",
                "doctor_query",
                "doctor_id",
                "appointment_id",
                "appointment_reference",
                "requested_date",
                "requested_start_time",
            )
        },
    }


def main() -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    meter = TokenMeter()
    semantic_decisions: list[dict[str, object]] = []
    original_interpreter = agent_chat_module.interpret_customer_turn

    def traced_interpreter(*args, **kwargs):
        decision = original_interpreter(*args, **kwargs)
        semantic_decisions.append(_small(decision))
        return decision

    agent_chat_module.interpret_customer_turn = traced_interpreter
    meter.install()
    mark = meter.mark()
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Workspace not found: tia")

        patient = _new_patient(db, workspace, 9921)
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
            started_at=now - timedelta(minutes=2),
            last_message_at=now - timedelta(minutes=1),
        )
        db.add(conversation)
        db.flush()

        db.add_all(
            [
                Message(
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                    sender_type="patient",
                    direction="inbound",
                    content="عايز ألغي معاد عندي.",
                    delivery_status="received",
                    metadata_json={},
                    created_at=now - timedelta(minutes=2),
                ),
                Message(
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                    sender_type="ai",
                    direction="outbound",
                    content=(
                        "عندك معادين مؤكدين:\n"
                        "- النهارده 11 سبتمبر الساعة 2:00 ظهرًا: ليزر إزالة الشعر – إبط مع د. أحمد محمود\n"
                        "- بكرة 12 سبتمبر من 10:00 لـ11:00 صباحًا: هيدرافيشل مع د. هالة مصطفى\n\n"
                        "تحب تلغي أنهي واحد؟"
                    ),
                    delivery_status="sent",
                    metadata_json={},
                    created_at=now - timedelta(minutes=1),
                ),
            ]
        )
        db.flush()

        response = agent_chat_module.run_agent_chat(
            db=db,
            workspace=workspace,
            payload=AgentChatRequest(
                patient_id=patient.id,
                conversation_id=conversation.id,
                channel="whatsapp",
                message="قصدي معاد الهيدرافيشل، سيب معاد الليزر زي ما هو.",
            ),
        )
        db.flush()
        db.refresh(laser)
        db.refresh(hydra)

        print(
            json.dumps(
                {
                    "assistant": response.reply,
                    "model": response.model,
                    "semantic": semantic_decisions[-1] if semantic_decisions else None,
                    "after": {"laser": laser.status, "hydra": hydra.status},
                    "actions": [
                        {
                            "tool": row.get("tool"),
                            "status": row.get("status"),
                            "appointment_id": row.get("appointment_id"),
                            "input": row.get("input"),
                        }
                        for row in _actions(db, workspace, patient)
                    ],
                    "tokens": meter.since(mark),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    finally:
        agent_chat_module.interpret_customer_turn = original_interpreter
        meter.uninstall()
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


if __name__ == "__main__":
    main()
