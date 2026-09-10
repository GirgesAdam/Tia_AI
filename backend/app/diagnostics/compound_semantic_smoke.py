from __future__ import annotations

"""Run exactly five read-only live semantic conversations for compound requests.

This module lives under ``app`` so it is included in the production/staging image.
It exercises Tia's configured LLM through the real semantic interpreter and clinic
catalog and performs no appointment or package writes.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.turn_interpreter import interpret_customer_turn
from app.core.config import settings
from app.models.workspace import Workspace


@dataclass(frozen=True)
class ConversationCase:
    name: str
    history: list[BaseMessage]
    check: Callable[[object, dict[str, str]], tuple[bool, str]]


def _catalog_row(catalog: dict, collection: str, name: str) -> dict:
    rows = [row for row in catalog.get(collection, []) if isinstance(row, dict)]
    exact = [row for row in rows if str(row.get("name") or "").strip() == name]
    if len(exact) == 1:
        return exact[0]
    suffix = [
        row
        for row in rows
        if str(row.get("name") or "").strip().endswith(" " + name)
    ]
    if len(suffix) == 1:
        return suffix[0]
    raise RuntimeError(f"Required catalog row not found or ambiguous: {collection}/{name}")


def _items(decision: object) -> list:
    return list(getattr(getattr(decision, "entity_hints"), "requested_items", []) or [])


def _compound_two_appointments(decision: object, expected: dict[str, str]) -> tuple[bool, str]:
    items = _items(decision)
    ok = (
        len(items) == 2
        and [item.kind for item in items] == ["appointment", "appointment"]
        and str(items[0].service_id or "") == expected["underarm"]
        and str(items[1].service_id or "") == expected["full_body"]
        and bool(items[0].requested_date)
        and bool(items[1].requested_date)
        and "appointment_creation" in set(getattr(decision, "capabilities", []) or [])
    )
    return ok, (
        f"kinds={[item.kind for item in items]} "
        f"services={[item.service_id for item in items]} "
        f"dates={[item.requested_date for item in items]}"
    )


def _compound_two_packages(decision: object, expected: dict[str, str]) -> tuple[bool, str]:
    items = _items(decision)
    ok = (
        len(items) == 2
        and [item.kind for item in items] == ["package_purchase", "package_purchase"]
        and str(items[0].service_id or "") == expected["full_body"]
        and items[0].package_sessions_count == 6
        and items[0].laser_device_key == "candela_gentle"
        and str(items[1].service_id or "") == expected["underarm"]
        and items[1].package_sessions_count == 3
        and items[1].laser_device_key == "prime_lase"
        and "package_purchase" in set(getattr(decision, "capabilities", []) or [])
    )
    return ok, (
        f"items={[(item.kind, item.service_id, item.package_sessions_count, item.laser_device_key) for item in items]}"
    )


def _package_then_first_session(decision: object, expected: dict[str, str]) -> tuple[bool, str]:
    items = _items(decision)
    ok = (
        len(items) == 2
        and [item.kind for item in items] == ["package_purchase", "appointment"]
        and str(items[0].service_id or "") == expected["full_body"]
        and items[0].package_sessions_count == 6
        and items[0].laser_device_key == "candela_gentle"
        and str(items[1].service_id or "") == expected["full_body"]
        and items[1].laser_device_key == "candela_gentle"
        and items[1].package_intent == "use_existing"
        and bool(items[1].requested_date)
        and "package_purchase" in set(getattr(decision, "capabilities", []) or [])
        and "appointment_creation" in set(getattr(decision, "capabilities", []) or [])
    )
    return ok, (
        f"items={[(item.kind, item.service_id, item.package_sessions_count, item.laser_device_key, item.package_intent, item.requested_date) for item in items]}"
    )


def _clarification_keeps_both_packages(decision: object, expected: dict[str, str]) -> tuple[bool, str]:
    return _compound_two_packages(decision, expected)


def _single_booking_stays_single(decision: object, expected: dict[str, str]) -> tuple[bool, str]:
    hints = getattr(decision, "entity_hints")
    items = _items(decision)
    ok = (
        items == []
        and str(hints.service_id or "") == expected["underarm"]
        and bool(hints.requested_date)
        and hints.requested_start_time == "18:00"
        and getattr(decision, "package_intent", "none") == "none"
        and "appointment_creation" in set(getattr(decision, "capabilities", []) or [])
    )
    return ok, (
        f"requested_items={len(items)} service={hints.service_id} "
        f"date={hints.requested_date} time={hints.requested_start_time} "
        f"package_intent={getattr(decision, 'package_intent', None)}"
    )


def _cases() -> list[ConversationCase]:
    return [
        ConversationCase(
            name="two_services_two_days",
            history=[HumanMessage(content="عايز احجز ليزر ابط السبت الجاي وكمان فول بادي يوم الأحد اللي بعده")],
            check=_compound_two_appointments,
        ),
        ConversationCase(
            name="two_packages_two_devices",
            history=[HumanMessage(content="عايز أشتري باكدج فول بادي 6 جلسات كانديلا وباكدج إبط 3 جلسات برايم ليز")],
            check=_compound_two_packages,
        ),
        ConversationCase(
            name="package_then_first_session",
            history=[HumanMessage(content="عايز باكدج فول بادي 6 جلسات كانديلا واحجزلي أول جلسة منه السبت الجاي")],
            check=_package_then_first_session,
        ),
        ConversationCase(
            name="compound_followup_clarification",
            history=[
                HumanMessage(content="عايز أشتري باكدج فول بادي 6 جلسات وكمان باكدج إبط 3 جلسات برايم ليز"),
                AIMessage(content="تمام، باكدج الفول بادي تحبه على كانديلا ولا برايم ليز؟"),
                HumanMessage(content="كانديلا"),
            ],
            check=_clarification_keeps_both_packages,
        ),
        ConversationCase(
            name="single_booking_regression",
            history=[HumanMessage(content="عايز احجز ليزر ابط السبت الجاي الساعة 6 بالليل")],
            check=_single_booking_stays_single,
        ),
    ]


def main() -> int:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(engine) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Workspace 'tia' not found.")
        catalog = build_clinic_catalog(db, workspace)
        underarm = _catalog_row(catalog, "services", "ليزر إزالة الشعر - إبط")
        full_body = _catalog_row(catalog, "services", "ليزر إزالة الشعر - جسم كامل سيدات")
        expected = {
            "underarm": str(underarm["id"]),
            "full_body": str(full_body["id"]),
        }
        timezone_name = (workspace.timezone or "Africa/Cairo").strip()
        local_now = datetime.now(ZoneInfo(timezone_name))
        failures = 0
        print("Running exactly 5 live compound semantic conversations", flush=True)
        for index, case in enumerate(_cases(), start=1):
            decision = interpret_customer_turn(
                flow=None,
                history=case.history,
                timezone_name=timezone_name,
                local_now=local_now,
                clinic_catalog=catalog,
            )
            ok, details = case.check(decision, expected)
            status = "PASS" if ok else "FAIL"
            failures += 0 if ok else 1
            latest = next(
                message.content
                for message in reversed(case.history)
                if isinstance(message, HumanMessage)
            )
            print(f"[{status}] {index}/5 {case.name}", flush=True)
            print(f"  customer: {latest}", flush=True)
            print(f"  capabilities: {list(decision.capabilities or [])}", flush=True)
            print(f"  {details}", flush=True)
        print(f"Summary: {5 - failures} passed, {failures} failed", flush=True)
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
