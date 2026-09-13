from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.patient_package import PackageUsage, PatientPackage
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.agent_v2.orchestrator import orchestrate_v2_turn
from app.services.patient_packages import package_read


REPORT_PATH = Path("artifacts/fix5-no-show-package-live-verification.json")


def main() -> int:
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Fix #5 live verification requires AGENT_V2_LIVE_ENABLED=true.")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    payload: dict[str, object] = {
        "runtime": "v2",
        "database_writes_persisted": False,
        "workspace_slug": "tia",
    }

    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Workspace 'tia' was not found.")

        candidates = db.execute(
            select(PatientPackage, PackageUsage, Appointment)
            .join(
                PackageUsage,
                (PackageUsage.workspace_id == PatientPackage.workspace_id)
                & (PackageUsage.patient_package_id == PatientPackage.id),
            )
            .join(
                Appointment,
                (Appointment.workspace_id == PackageUsage.workspace_id)
                & (Appointment.id == PackageUsage.appointment_id),
            )
            .where(
                PatientPackage.workspace_id == workspace.id,
                PackageUsage.status == "released",
                Appointment.status == "no_show",
            )
            .order_by(Appointment.start_at.desc())
        ).all()

        selected = None
        for package, usage, appointment in candidates:
            snapshot = package_read(db, package)
            if snapshot.sessions_remaining == 4:
                selected = (package, usage, appointment, snapshot)
                break
        if selected is None:
            raise RuntimeError(
                "No staging no-show/released package case with verified remaining balance 4 was found."
            )

        package, usage, appointment, snapshot = selected
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == workspace.id,
                Patient.id == package.patient_id,
            )
        )
        service = db.scalar(
            select(Service).where(
                Service.workspace_id == workspace.id,
                Service.id == package.service_id,
            )
        )
        if patient is None or service is None:
            raise RuntimeError("Selected staging package case is missing patient/service data.")

        question = (
            f"أنا ماحضرتش جلسة {service.name} اللي فاتت. "
            "هل الجلسة دي اتحسبت من الباكدج؟ وفاضلي كام جلسة دلوقتي؟"
        )
        now = datetime.now(UTC).astimezone(ZoneInfo(workspace.timezone))
        turn = orchestrate_v2_turn(
            db=db,
            workspace=workspace,
            patient=patient,
            conversation_id=uuid4(),
            run_id=uuid4(),
            history=[HumanMessage(content=question)],
            local_now=now,
            timezone_name=workspace.timezone,
            clinic_name=workspace.name,
        )

        operations = [operation.type for operation in turn.understanding.operations]
        read_kinds = [kind for trace in turn.traces for kind in trace.read_kinds]
        write_intents = [
            step.write_intent.kind
            for step in turn.plan.steps
            if step.write_intent is not None
        ]

        payload.update(
            {
                "question": question,
                "verified_db_facts": {
                    "appointment_status": appointment.status,
                    "usage_status": usage.status,
                    "package_status": package.status,
                    "sessions_purchased": snapshot.sessions_purchased,
                    "sessions_reserved": snapshot.sessions_reserved,
                    "sessions_consumed": snapshot.sessions_consumed,
                    "sessions_remaining": snapshot.sessions_remaining,
                },
                "semantic_operations": operations,
                "read_kinds": read_kinds,
                "write_intents": write_intents,
                "pending_write": turn.pending_write is not None,
                "reply": turn.reply,
                "responder_model": turn.responder_model,
            }
        )

        required_operations = {"customer_history", "package_info"}
        required_reads = {"customer_history", "customer_packages"}
        if not required_operations.issubset(set(operations)):
            raise AssertionError(
                f"Missing semantic decomposition: expected {sorted(required_operations)}, got {operations}."
            )
        if not required_reads.issubset(set(read_kinds)):
            raise AssertionError(
                f"Missing verified read composition: expected {sorted(required_reads)}, got {read_kinds}."
            )
        if write_intents or turn.pending_write is not None:
            raise AssertionError("Fix #5 verification must remain read-only.")
        if snapshot.sessions_remaining != 4:
            raise AssertionError("Selected package balance changed from the expected verified value 4.")
        if turn.reply is None or "4" not in turn.reply:
            raise AssertionError(
                f"Customer reply did not surface the verified remaining balance 4: {turn.reply!r}"
            )

        payload["passed"] = True
        return_code = 0
    except Exception as exc:  # noqa: BLE001
        payload["passed"] = False
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return_code = 1
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
        print(f"Report: {REPORT_PATH.resolve()}", flush=True)

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
