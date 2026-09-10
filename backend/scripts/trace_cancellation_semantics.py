from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.turn_interpreter import interpret_customer_turn
from app.core.config import settings
from app.models.workspace import Workspace
from app.services.agent_chat import _with_current_patient_appointments
from scripts.run_realistic_system_journeys import (
    HYDRA,
    UNDERARM,
    TokenMeter,
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
    meter.install()
    mark = meter.mark()
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Workspace not found: tia")
        patient = _new_patient(db, workspace, 9911)
        laser_slot = _find_slot(db, workspace, UNDERARM, laser_device_key="prime_lase")
        laser = _seed_appointment(db, workspace, patient, laser_slot)
        hydra_slot = _find_slot(db, workspace, HYDRA, avoid=[(laser.start_at, laser.end_at)])
        _seed_appointment(db, workspace, patient, hydra_slot)
        db.flush()

        catalog = build_clinic_catalog(db, workspace)
        catalog = _with_current_patient_appointments(
            db=db,
            workspace=workspace,
            patient=patient,
            clinic_catalog=catalog,
        )
        appointments = list(catalog.get("appointments") or [])
        if len(appointments) != 2:
            raise RuntimeError(f"Expected exactly two upcoming appointments, got {len(appointments)}")

        listing = "\n".join(
            f"{idx}. {row['service_name']}: {row['start_local']} مع {row['doctor_name']}"
            for idx, row in enumerate(appointments, start=1)
        )
        history = [
            HumanMessage(content="عايز ألغي معاد عندي."),
            AIMessage(content=f"عندك معادين مؤكدين، تحب تلغي أنهي واحد؟\n{listing}"),
            HumanMessage(content="قصدي معاد الهيدرافيشل، سيب معاد الليزر زي ما هو."),
        ]
        timezone_name = workspace.timezone or "Africa/Cairo"
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            timezone_name = "Africa/Cairo"
            tz = ZoneInfo(timezone_name)

        decision = interpret_customer_turn(
            flow=None,
            history=history,
            timezone_name=timezone_name,
            local_now=datetime.now(tz),
            clinic_catalog=catalog,
        )
        usage = meter.since(mark)
        print(
            json.dumps(
                {
                    "catalog_appointments": appointments,
                    "decision": decision.model_dump(mode="json"),
                    "tokens": usage,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    finally:
        meter.uninstall()
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


if __name__ == "__main__":
    main()
