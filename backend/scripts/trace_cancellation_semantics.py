from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.services.agent_chat as agent_chat_module
from app.core.config import settings
from app.models.conversation_flow_state import ConversationFlowState
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
        semantic_decisions.append(decision.model_dump(mode="json"))
        return decision

    agent_chat_module.interpret_customer_turn = traced_interpreter
    meter.install()
    mark = meter.mark()
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Workspace not found: tia")

        patient = _new_patient(db, workspace, 9914)
        laser_slot = _find_slot(db, workspace, UNDERARM, laser_device_key="prime_lase")
        _seed_appointment(db, workspace, patient, laser_slot)
        hydra_slot = _find_slot(db, workspace, HYDRA, avoid=[(laser_slot.start_at, laser_slot.end_at)])
        _seed_appointment(db, workspace, patient, hydra_slot)

        response = agent_chat_module.run_agent_chat(
            db=db,
            workspace=workspace,
            payload=AgentChatRequest(
                patient_id=patient.id,
                channel="whatsapp",
                message="عايز ألغي معاد عندي.",
            ),
        )
        db.flush()

        flows = list(
            db.scalars(
                select(ConversationFlowState)
                .where(
                    ConversationFlowState.workspace_id == workspace.id,
                    ConversationFlowState.conversation_id == response.conversation_id,
                )
                .order_by(ConversationFlowState.created_at.asc())
            )
        )
        messages = list(
            db.scalars(
                select(Message)
                .where(
                    Message.workspace_id == workspace.id,
                    Message.conversation_id == response.conversation_id,
                )
                .order_by(Message.created_at.asc())
            )
        )
        usage = meter.since(mark)

        print(
            json.dumps(
                {
                    "assistant": response.reply,
                    "model": response.model,
                    "semantic_decisions": semantic_decisions,
                    "flows": [
                        {
                            "flow_type": flow.flow_type,
                            "status": flow.status,
                            "is_active": flow.is_active,
                            "capabilities": flow.capabilities,
                            "entity_state": flow.entity_state,
                            "missing_information": flow.missing_information,
                            "option_snapshot": flow.option_snapshot,
                            "last_decision": flow.last_decision,
                        }
                        for flow in flows
                    ],
                    "actions": _actions(db, workspace, patient),
                    "messages": [
                        {
                            "sender_type": message.sender_type,
                            "direction": message.direction,
                            "content": message.content,
                            "metadata": message.metadata_json,
                        }
                        for message in messages
                    ],
                    "tokens": usage,
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
