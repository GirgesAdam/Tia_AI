from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.services.agent_chat as agent_chat_module
from app.core.config import settings
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
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Workspace not found: tia")

        patient = _new_patient(db, workspace, 9915)
        laser_slot = _find_slot(db, workspace, UNDERARM, laser_device_key="prime_lase")
        laser = _seed_appointment(db, workspace, patient, laser_slot)
        hydra_slot = _find_slot(db, workspace, HYDRA, avoid=[(laser.start_at, laser.end_at)])
        hydra = _seed_appointment(db, workspace, patient, hydra_slot)

        mark1 = meter.mark()
        first = agent_chat_module.run_agent_chat(
            db=db,
            workspace=workspace,
            payload=AgentChatRequest(
                patient_id=patient.id,
                channel="whatsapp",
                message="عايز ألغي معاد عندي.",
            ),
        )
        usage1 = meter.since(mark1)

        mark2 = meter.mark()
        second = agent_chat_module.run_agent_chat(
            db=db,
            workspace=workspace,
            payload=AgentChatRequest(
                patient_id=patient.id,
                conversation_id=first.conversation_id,
                channel="whatsapp",
                message="قصدي معاد الهيدرافيشل، سيب معاد الليزر زي ما هو.",
            ),
        )
        usage2 = meter.since(mark2)
        db.flush()
        db.refresh(laser)
        db.refresh(hydra)

        print(
            json.dumps(
                {
                    "turn1": {
                        "assistant": first.reply,
                        "model": first.model,
                        "semantic": semantic_decisions[0] if semantic_decisions else None,
                        "tokens": usage1,
                    },
                    "turn2": {
                        "assistant": second.reply,
                        "model": second.model,
                        "semantic": semantic_decisions[1] if len(semantic_decisions) > 1 else None,
                        "tokens": usage2,
                    },
                    "after": {"laser": laser.status, "hydra": hydra.status},
                    "actions": [
                        {
                            "tool": row.get("tool"),
                            "status": row.get("status"),
                            "appointment_id": row.get("appointment_id"),
                        }
                        for row in _actions(db, workspace, patient)
                    ],
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
