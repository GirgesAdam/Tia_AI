from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from supabase import create_client

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.models.conversation_flow_event import ConversationFlowEvent
from app.models.conversation_flow_state import ConversationFlowState
from staging_scenarios import REGRESSION_WORKSPACE_ID, sid

DEFAULT_EMAIL = "adam1ezzat1@gmail.com"
DEFAULT_WORKSPACE_ID = str(REGRESSION_WORKSPACE_ID)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()

    passed = warned = failed = 0
    lines: list[str] = []

    def result(name: str, state: str, detail: str = ""):
        nonlocal passed, warned, failed
        if state == "PASS":
            passed += 1
        elif state == "WARN":
            warned += 1
        else:
            failed += 1
        line = f"[{state}] {name}" + (f" — {detail}" if detail else "")
        print(line)
        lines.append(line)

    if settings.is_production:
        result("Production safety gate", "FAIL", "Refusing production.")
        return 2

    if not args.no_seed:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "seed_full_staging_demo.py")],
            cwd=str(BACKEND_DIR),
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            result("Reset staging scenarios", "FAIL", f"exit={proc.returncode}")
            return 2
        result("Reset staging scenarios", "PASS")

    password = input("Supabase password: ")
    auth = create_client(
        settings.supabase_url,
        settings.supabase_publishable_key,
    ).auth.sign_in_with_password({"email": args.email, "password": password})
    token = auth.session.access_token
    result("Supabase login", "PASS")

    wid = UUID(args.workspace_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(wid),
    }
    base = args.base_url.rstrip("/") + "/api/v1"
    client = httpx.Client(timeout=180.0)

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    booking_patient = sid(wid, "patient:agent_booking")
    medical_patient = sid(wid, "patient:handoff_medical")

    def chat(name: str, body: dict, predicate):
        started = time.perf_counter()
        response = client.post(base + "/agent/chat", headers=headers, json=body)
        elapsed = time.perf_counter() - started
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}
        print(f"\n--- {name} ---\nHTTP={response.status_code} TIME={elapsed:.2f}s")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        ok = response.status_code == 200 and predicate(data)
        result(name, "PASS" if ok else "FAIL", f"HTTP {response.status_code}")
        if args.pause_seconds > 0:
            time.sleep(args.pause_seconds)
        return data

    booking_date = (
        datetime.now(ZoneInfo("Africa/Cairo")).date() + timedelta(days=3)
    ).isoformat()

    first = chat(
        "Combined pricing + booking discovery",
        {
            "patient_id": str(booking_patient),
            "channel": "web",
            "message": (
                f"قولي سعر ليزر ريجريشن وعايز أحجز يوم {booking_date} "
                "في Regression Cairo Branch مع د. ريجريشن الأول بعد 6 مساء"
            ),
        },
        lambda d: bool(d.get("conversation_id") and d.get("reply")),
    )

    conversation_id = first.get("conversation_id") if isinstance(first, dict) else None
    if conversation_id:
        with SessionLocal() as db:
            flow = db.scalar(
                select(ConversationFlowState).where(
                    ConversationFlowState.workspace_id == wid,
                    ConversationFlowState.conversation_id == UUID(conversation_id),
                    ConversationFlowState.is_active.is_(True),
                )
            )
            result(
                "Booking flow persisted",
                "PASS"
                if flow is not None
                and flow.flow_type == "booking"
                and flow.status == "awaiting_option_selection"
                else "FAIL",
                f"status={getattr(flow, 'status', None)} version={getattr(flow, 'version', None)}",
            )
            first_version = flow.version if flow else None

        second = chat(
            "Active flow structured option selection",
            {
                "patient_id": str(booking_patient),
                "conversation_id": conversation_id,
                "channel": "web",
                "message": "خلاص اختار أول ميعاد من المواعيد اللي عرضتها",
            },
            lambda d: (
                d.get("outbound_message_id")
                and d.get("model") == "flow-interpreter:deterministic-booking"
            ),
        )

        appointments = client.get(
            base + f"/booking/appointments?patient_id={booking_patient}&limit=20",
            headers=headers,
        )
        rows = appointments.json() if appointments.status_code == 200 else []
        result(
            "Stateful booking persisted in PostgreSQL",
            "PASS"
            if any(
                item.get("status") in {"pending", "confirmed"}
                for item in rows
                if isinstance(item, dict)
            )
            else "FAIL",
            f"HTTP {appointments.status_code}",
        )

        with SessionLocal() as db:
            flow = db.scalar(
                select(ConversationFlowState)
                .where(
                    ConversationFlowState.workspace_id == wid,
                    ConversationFlowState.conversation_id == UUID(conversation_id),
                )
                .order_by(ConversationFlowState.created_at.desc())
                .limit(1)
            )
            result(
                "Booking flow completed and version advanced",
                "PASS"
                if flow is not None
                and flow.status == "completed"
                and flow.is_active is False
                and (first_version is None or flow.version > first_version)
                else "FAIL",
                f"status={getattr(flow, 'status', None)} version={getattr(flow, 'version', None)}",
            )
            events = list(
                db.scalars(
                    select(ConversationFlowEvent).where(
                        ConversationFlowEvent.flow_state_id == flow.id
                    )
                )
            ) if flow else []
            event_types = {event.event_type for event in events}
            result(
                "Flow audit trail contains start/options/write/complete",
                "PASS"
                if {"started", "options_presented", "write_authorized", "write_completed", "completed"}.issubset(event_types)
                else "FAIL",
                f"events={sorted(event_types)}",
            )
    else:
        result("Booking flow persisted", "FAIL", "No conversation_id.")
        result("Stateful booking persisted in PostgreSQL", "FAIL")
        result("Booking flow completed and version advanced", "FAIL")
        result("Flow audit trail contains start/options/write/complete", "FAIL")

    # New booking flow interrupted by medical risk.
    medical_start = chat(
        "Start booking flow for safety interruption test",
        {
            "patient_id": str(medical_patient),
            "channel": "web",
            "message": f"عايزة أشوف مواعيد ليزر ريجريشن يوم {booking_date} بعد 6",
        },
        lambda d: bool(d.get("conversation_id")),
    )
    medical_conversation = (
        medical_start.get("conversation_id")
        if isinstance(medical_start, dict)
        else None
    )
    if medical_conversation:
        medical = chat(
            "Medical question interrupts active booking flow",
            {
                "patient_id": str(medical_patient),
                "conversation_id": medical_conversation,
                "channel": "web",
                "message": "أنا حامل، هل الخدمة دي مناسبة ليا طبيًا؟",
            },
            lambda d: d.get("handoff_required") is True,
        )
        with SessionLocal() as db:
            flow = db.scalar(
                select(ConversationFlowState)
                .where(
                    ConversationFlowState.workspace_id == wid,
                    ConversationFlowState.conversation_id == UUID(medical_conversation),
                )
                .order_by(ConversationFlowState.created_at.desc())
                .limit(1)
            )
            result(
                "Medical interruption closes active flow",
                "PASS"
                if flow is not None
                and flow.status == "interrupted"
                and flow.is_active is False
                else "FAIL",
                f"status={getattr(flow, 'status', None)}",
            )
    else:
        result("Medical question interrupts active booking flow", "FAIL")
        result("Medical interruption closes active flow", "FAIL")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path.cwd() / f"tia_agent_stateful_regression_{stamp}.txt"
    lines.append(f"SUMMARY PASS={passed} WARN={warned} FAIL={failed}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSUMMARY PASS={passed} WARN={warned} FAIL={failed}")
    print(f"Results saved to: {path}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
