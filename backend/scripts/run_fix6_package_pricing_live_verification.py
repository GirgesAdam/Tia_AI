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
from app.models.patient import Patient
from app.models.service import Service
from app.models.service_package_offer import ServicePackageOffer
from app.models.workspace import Workspace
from app.services.agent_v2.orchestrator import orchestrate_v2_turn


REPORT_PATH = Path("artifacts/fix6-package-pricing-live-verification.json")
TARGET_SERVICE_NAME = "ليزر إزالة الشعر - إبط"
TARGET_DEVICE_KEY = "prime_lase"
TARGET_SESSIONS = 6
TARGET_PRICE_MINOR = 295000
SINGLE_PRICE_MINOR = 55000


def _normalized_digits(value: str) -> str:
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return value.translate(table).replace(",", "").replace("٬", "").replace(" ", "")


def main() -> int:
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Fix #6 live verification requires AGENT_V2_LIVE_ENABLED=true.")

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

        row = db.execute(
            select(ServicePackageOffer, Service)
            .join(
                Service,
                (Service.workspace_id == ServicePackageOffer.workspace_id)
                & (Service.id == ServicePackageOffer.service_id),
            )
            .where(
                ServicePackageOffer.workspace_id == workspace.id,
                Service.name == TARGET_SERVICE_NAME,
                ServicePackageOffer.device_key == TARGET_DEVICE_KEY,
                ServicePackageOffer.sessions_count == TARGET_SESSIONS,
                ServicePackageOffer.is_active.is_(True),
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("Target staging 6-session Prime Lase underarm package offer was not found.")
        offer, service = row

        if offer.price_minor != TARGET_PRICE_MINOR:
            raise AssertionError(
                f"Target package price changed: expected {TARGET_PRICE_MINOR}, got {offer.price_minor}."
            )
        if service.price_minor != SINGLE_PRICE_MINOR:
            raise AssertionError(
                f"Target single-session price changed: expected {SINGLE_PRICE_MINOR}, got {service.price_minor}."
            )

        patient = db.scalar(
            select(Patient)
            .where(Patient.workspace_id == workspace.id)
            .order_by(Patient.created_at.asc(), Patient.id.asc())
        )
        if patient is None:
            raise RuntimeError("No staging patient was available for the read-only pricing turn.")

        question = f"باكدج {TARGET_SESSIONS} جلسات {service.name} على {offer.device_name} بكام؟"
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

        semantic_operations = [operation.type for operation in turn.understanding.operations]
        semantic_details = [
            {
                "type": operation.type,
                "service_ref": operation.entities.service.ref if operation.entities.service else None,
                "device_ref": operation.entities.device.ref if operation.entities.device else None,
                "package_sessions": operation.entities.package_sessions,
                "execution_intent": operation.execution_intent,
            }
            for operation in turn.understanding.operations
        ]
        read_kinds = [kind for trace in turn.traces for kind in trace.read_kinds]
        write_intents = [
            step.write_intent.kind
            for step in turn.plan.steps
            if step.write_intent is not None
        ]
        plan_reads = [
            {
                "operation_type": step.operation_type,
                "read_kinds": [read.kind for read in step.reads],
                "parameters": [read.parameters for read in step.reads],
            }
            for step in turn.plan.steps
        ]
        outcomes = [outcome.model_dump(mode="json") for outcome in turn.outcomes]

        payload.update(
            {
                "question": question,
                "verified_db_facts": {
                    "service_name": service.name,
                    "single_session_price_minor": service.price_minor,
                    "package_device_key": offer.device_key,
                    "package_device_name": offer.device_name,
                    "package_sessions": offer.sessions_count,
                    "package_price_minor": offer.price_minor,
                    "currency": offer.currency,
                },
                "semantic_operations": semantic_operations,
                "semantic_details": semantic_details,
                "plan_reads": plan_reads,
                "read_kinds": read_kinds,
                "write_intents": write_intents,
                "pending_write": turn.pending_write is not None,
                "outcomes": outcomes,
                "reply": turn.reply,
                "responder_model": turn.responder_model,
            }
        )

        pricing_operations = [
            operation
            for operation in turn.understanding.operations
            if operation.type == "pricing"
        ]
        if len(pricing_operations) != 1:
            raise AssertionError(
                f"Expected one pricing operation, got {semantic_operations}."
            )
        pricing = pricing_operations[0]
        if pricing.entities.package_sessions != TARGET_SESSIONS:
            raise AssertionError(
                "Interpreter did not preserve the explicit package session count: "
                f"expected {TARGET_SESSIONS}, got {pricing.entities.package_sessions}."
            )
        if pricing.execution_intent != "informational":
            raise AssertionError(
                f"Package price question must stay informational, got {pricing.execution_intent}."
            )
        if read_kinds != ["package_offers"]:
            raise AssertionError(
                f"Package pricing must use only package_offers, got {read_kinds}."
            )
        if write_intents or turn.pending_write is not None:
            raise AssertionError("Fix #6 package pricing verification must remain read-only.")

        package_steps = [
            step
            for step in turn.plan.steps
            if any(read.kind == "package_offers" for read in step.reads)
        ]
        if len(package_steps) != 1:
            raise AssertionError("Expected exactly one package_offers planner step.")
        parameters = package_steps[0].reads[0].parameters
        if parameters.get("service_id") != str(service.id):
            raise AssertionError("Planner did not resolve the requested service to the target offer.")
        if parameters.get("device_key") != TARGET_DEVICE_KEY:
            raise AssertionError("Planner did not preserve the requested Prime Lase device.")
        if parameters.get("package_sessions") != TARGET_SESSIONS:
            raise AssertionError("Planner did not preserve the requested six-session package dimension.")

        reply = turn.reply or ""
        compact_reply = _normalized_digits(reply)
        if "2950" not in compact_reply:
            raise AssertionError(
                f"Customer reply did not surface the verified package price 2950 EGP: {reply!r}"
            )
        if "550" in compact_reply and "2950" not in compact_reply:
            raise AssertionError(
                f"Customer reply fell back to the single-session price 550 EGP: {reply!r}"
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
