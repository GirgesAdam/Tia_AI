from __future__ import annotations

"""Manual semantic review for the fixes + five longer booking conversations.

Ten conversations, each 5-10 customer turns. Real staging LLM/DB adapter, one
rollback-isolated transaction per conversation. No automated PASS/FAIL quality
labels and no WhatsApp/n8n delivery.
"""

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.appointment import Appointment
from app.models.conversation import Conversation
from app.models.patient import Patient
from app.models.patient_package import PatientPackage
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.patient_packages import create_patient_package
from scripts.run_daily_clinic_conversation_review import (
    _actions_for_conversation,
    _appointment_snapshot,
    _base_patient,
    _booking_context,
    _generic_context,
    _package_snapshot,
    _seed_upcoming,
    _send,
    _slot_text,
)

CASES = (
    "fixed_clinic_info",
    "fixed_payment_status",
    "fixed_exact_reschedule",
    "fixed_package_prepaid_wording",
    "multiple_same_service_packages",
    "booking_reject_days_then_return",
    "booking_exact_time_unavailable_then_flexible",
    "booking_change_service_mid_conversation",
    "reschedule_two_appointments_choose_one",
    "booking_time_constraints_keep_changing",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument(
        "--report",
        default="artifacts/extended-booking-conversation-review.json",
    )
    return parser.parse_args()


def _catalog_row(catalog: dict, collection: str, row_id: UUID) -> dict | None:
    return next(
        (
            row
            for row in catalog.get(collection, [])
            if isinstance(row, dict) and str(row.get("id") or "") == str(row_id)
        ),
        None,
    )


def _future_days_for(
    db: Session,
    workspace: Workspace,
    *,
    service: dict,
    doctor: dict,
    count: int = 3,
    after_hour: int | None = None,
    exclude_appointment_id: UUID | None = None,
) -> list[tuple[date, object, list[object]]]:
    branch_id = str(workspace.primary_branch_id or "")
    if not branch_id:
        raise RuntimeError("No primary location")
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    today = datetime.now(UTC).date()
    found: list[tuple[date, object, list[object]]] = []
    for offset in range(1, 50):
        day = today + timedelta(days=offset)
        result = adapter.get_availability(
            AvailabilityRequest(
                branch_id=branch_id,
                service_id=str(service["id"]),
                booking_date=day,
                doctor_id=str(doctor["id"]),
                exclude_appointment_id=(str(exclude_appointment_id) if exclude_appointment_id else None),
            )
        )
        slots = list(result.slots)
        if after_hour is not None:
            tz = ZoneInfo(result.timezone)
            slots = [slot for slot in slots if slot.start_at.astimezone(tz).hour >= after_hour]
        if slots:
            found.append((day, result, slots))
            if len(found) >= count:
                return found
    if len(found) < count:
        raise RuntimeError(f"Only found {len(found)} usable future days")
    return found


def _service_and_doctor_for_appointment(
    db: Session,
    workspace: Workspace,
    appointment: Appointment,
) -> tuple[dict, dict]:
    catalog = build_clinic_catalog(db, workspace)
    service = _catalog_row(catalog, "services", appointment.service_id)
    doctor = _catalog_row(catalog, "doctors", appointment.doctor_id)
    if service is None or doctor is None:
        raise RuntimeError("Fixture appointment is not grounded in active catalog")
    return service, doctor


def _new_second_package(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    *,
    service_id: UUID,
    booking_day: date,
    suffix: str,
) -> PatientPackage:
    service = db.scalar(
        select(Service).where(
            Service.workspace_id == workspace.id,
            Service.id == service_id,
        )
    )
    if service is None:
        raise RuntimeError("Service missing")
    now = datetime.now(UTC)
    return create_patient_package(
        db,
        workspace_id=workspace.id,
        patient_id=patient.id,
        service_id=service.id,
        name=f"باكدج إضافية {service.name} {suffix}",
        sessions_purchased=4,
        sale_price_minor=max(int(service.price_minor) * 3, 0),
        amount_paid_minor=0,
        payment_method="unknown",
        created_by_user_id=None,
        purchased_at=now,
        expires_at=booking_day + timedelta(days=7),
        idempotency_key=f"extended-review-{suffix}-{patient.id}",
        actor_type="system",
    )


def _setup_case(
    name: str,
    db: Session,
    workspace: Workspace,
) -> tuple[Patient, list[str], str]:
    patient = _base_patient(db, workspace)

    if name == "fixed_clinic_info":
        return (
            patient,
            [
                "العنوان ومواعيد الشغل إيه؟",
                "طب النهاردة مواعيدكم من كام لكام؟",
                "ورقم التليفون لو موجود؟",
                "تمام، أنا مش هحجز دلوقتي.",
                "أكدلي العنوان بس في سطر واحد.",
            ],
            "Clinic info should answer verified address/hours directly without inventing a branch concept.",
        )

    if name == "fixed_payment_status":
        row = _seed_upcoming(db, workspace, patient, 1)[0]
        row.payment_status = "paid"
        row.amount_paid_minor = row.price_minor
        row.payment_method = "card"
        db.flush()
        return (
            patient,
            [
                "فكرني بمعادي الجاي.",
                "هو الميعاد ده مدفوع ولا لسه؟",
                "دفعت بإيه؟",
                "يعني المبلغ بتاع الحجز ده متسجل مدفوع كامل؟",
                "تمام، متغيرش أي حاجة في الحجز.",
            ],
            "Own verified payment facts should be answered directly; no payment handoff for a read-only question.",
        )

    if name == "fixed_exact_reschedule":
        row = _seed_upcoming(db, workspace, patient, 1)[0]
        service, doctor = _service_and_doctor_for_appointment(db, workspace, row)
        days = _future_days_for(
            db,
            workspace,
            service=service,
            doctor=doctor,
            count=1,
            exclude_appointment_id=row.id,
        )
        _, available, slots = days[0]
        date_text, time_text = _slot_text(available, slots[-1])
        return (
            patient,
            [
                "فكرني بمعادي الجاي.",
                "عايز أغيره.",
                f"غيّره ليوم {date_text} الساعة {time_text} مع {doctor.get('name') or 'نفس الدكتور'}.",
                "تمام، فكرني بالميعاد بعد التغيير.",
                "خلاص كده، متغيرش حاجة تانية.",
            ],
            "A clear exact reschedule command should execute after availability verification without redundant confirmation.",
        )

    if name in {"fixed_package_prepaid_wording", "multiple_same_service_packages"}:
        _, service, doctor, _, _, available = _booking_context(db, workspace)
        slot = available.slots[0]
        date_text, time_text = _slot_text(available, slot)
        service_id = UUID(str(service["id"]))
        _new_second_package(
            db,
            workspace,
            patient,
            service_id=service_id,
            booking_day=date.fromisoformat(date_text),
            suffix=f"{name}-a",
        )
        if name == "multiple_same_service_packages":
            later = create_patient_package(
                db,
                workspace_id=workspace.id,
                patient_id=patient.id,
                service_id=service_id,
                name=f"باكدج ثانية {service.get('name')}",
                sessions_purchased=6,
                sale_price_minor=0,
                amount_paid_minor=0,
                payment_method="unknown",
                created_by_user_id=None,
                purchased_at=datetime.now(UTC) + timedelta(seconds=1),
                expires_at=date.fromisoformat(date_text) + timedelta(days=21),
                idempotency_key=f"extended-review-{name}-b-{patient.id}",
                actor_type="system",
            )
            del later
            messages = [
                f"أنا عندي أكتر من باكدج لـ{service.get('name')} صح؟",
                "عايز أحجز الجلسة الجاية من واحدة منهم.",
                f"خليها مع {doctor.get('name')} يوم {date_text}.",
                f"الساعة {time_text} مناسبة، احجزها من الباكدج.",
                "أنهي باكدج اتحسبت منها الجلسة؟",
                "وفاضلي كام جلسة فيها بعد الحجز؟",
            ]
            purpose = "Multiple active same-service packages are allowed; booking consumes one deterministic package only."
        else:
            messages = [
                f"عندي باكدج {service.get('name')} وعايز أحجز منها.",
                f"إيه المتاح مع {doctor.get('name')} يوم {date_text}؟",
                f"تمام الساعة {time_text} مناسبة، احجزها من الباكدج.",
                "الحجز ده محتاج أدفع له مبلغ جديد؟",
                "وفاضلي كام جلسة بعد الحجز؟",
            ]
            purpose = "A package booking should clearly say it consumed prepaid entitlement and does not require a new session payment."
        return patient, messages, purpose

    if name == "booking_reject_days_then_return":
        _, service, doctor, _, _, _ = _booking_context(db, workspace)
        days = _future_days_for(db, workspace, service=service, doctor=doctor, count=3)
        d1, a1, s1 = days[0]
        d2, _, _ = days[1]
        d3, _, _ = days[2]
        _, chosen_time = _slot_text(a1, s1[0])
        return (
            patient,
            [
                f"عايز أحجز {service.get('name')} مع {doctor.get('name')} أقرب ميعاد متاح.",
                "اليوم ده مش مناسب، عايز يوم تاني.",
                f"طب يوم {d3.isoformat()} فيه؟",
                f"لا خلاص خلينا يوم {d1.isoformat()} اللي قولته الأول.",
                f"الساعة {chosen_time} مناسبة.",
                "فكرني بتفاصيل الحجز اللي اتعمل.",
                "تمام، متغيرش حاجة.",
            ],
            f"Reject {d1}, inspect later dates including {d2}/{d3}, return to the original day, then book an exact evening time.",
        )

    if name == "booking_exact_time_unavailable_then_flexible":
        _, service, doctor, _, _, available = _booking_context(db, workspace)
        real_slot = available.slots[-1]
        date_text, real_time = _slot_text(available, real_slot)
        return (
            patient,
            [
                f"عايز أحجز {service.get('name')} مع {doctor.get('name')} يوم {date_text} الساعة 14:07.",
                "لو 14:07 مش متاح متحجزش وقت قريب من نفسك.",
                "طب وريني المتاح في نفس اليوم.",
                "المواعيد بدري عليا، عايز حاجة متأخرة أكتر.",
                f"لو الساعة {real_time} متاحة احجزها.",
                "قولي تفاصيل الميعاد النهائي.",
            ],
            "Exact unavailable minute must remain exact; customer later relaxes the constraint and explicitly chooses a verified slot.",
        )

    if name == "booking_change_service_mid_conversation":
        _, first_service, _, _, first_day, _ = _booking_context(db, workspace)
        _, second_service, second_doctor, _, second_day, second_available = _booking_context(
            db,
            workspace,
            exclude_service_id=str(first_service["id"]),
        )
        _, final_time = _slot_text(second_available, second_available.slots[0])
        return (
            patient,
            [
                f"عايز أحجز {first_service.get('name')} يوم {first_day.isoformat()}.",
                "لا المواعيد دي مش مناسبة.",
                f"غيرت رأيي، عايز {second_service.get('name')} بدلها.",
                f"شوفلي {second_service.get('name')} مع {second_doctor.get('name')} يوم {second_day.isoformat()}.",
                f"عايز النسخة اللي مدتها {int(second_service.get('duration_minutes') or 0)} دقيقة.",
                f"الساعة {final_time} مناسبة، احجزها.",
                "أكدلي إن الحجز للخدمة الجديدة مش الأولى.",
            ],
            "Changing service mid-flow must clear stale service/doctor constraints and only book the newly requested service.",
        )

    if name == "reschedule_two_appointments_choose_one":
        rows = _seed_upcoming(db, workspace, patient, 2)
        target = rows[0]
        service, doctor = _service_and_doctor_for_appointment(db, workspace, target)
        days = _future_days_for(
            db,
            workspace,
            service=service,
            doctor=doctor,
            count=2,
            exclude_appointment_id=target.id,
        )
        first_day, _, _ = days[0]
        second_day, second_available, second_slots = days[1]
        _, final_time = _slot_text(second_available, second_slots[0])
        target_local = target.start_at.astimezone(ZoneInfo(workspace.timezone or "Africa/Cairo"))
        return (
            patient,
            [
                "عايز أغير معادي.",
                f"قصدي الميعاد اللي يوم {target_local.date().isoformat()} الساعة {target_local.strftime('%H:%M')}.",
                f"شوفلي بدل منه يوم {first_day.isoformat()}.",
                "لا اليوم ده مش مناسب برضه.",
                f"طب يوم {second_day.isoformat()}؟",
                f"الساعة {final_time} مناسبة، غيره للوقت ده.",
                "فكرني بكل مواعيدي الجاية بعد التغيير.",
            ],
            "With two appointments, select one explicitly, reject one replacement day, then reschedule only the selected appointment.",
        )

    if name == "booking_time_constraints_keep_changing":
        _, service, doctor, _, _, _ = _booking_context(db, workspace)
        days = _future_days_for(db, workspace, service=service, doctor=doctor, count=2)
        d1, a1, slots1 = days[0]
        d2, a2, slots2 = days[1]
        tz1 = ZoneInfo(a1.timezone)
        early = min(slots1, key=lambda slot: slot.start_at)
        late = max(slots2, key=lambda slot: slot.start_at)
        _, early_time = _slot_text(a1, early)
        _, late_time = _slot_text(a2, late)
        early_hour = early.start_at.astimezone(tz1).hour
        return (
            patient,
            [
                f"عايز أحجز {service.get('name')} مع {doctor.get('name')} يوم {d1.isoformat()}.",
                f"محتاجه بعد الساعة {max(early_hour + 1, 12)}.",
                "لا، خلينا يوم تاني خالص.",
                f"شوف يوم {d2.isoformat()}، ومش لازم نفس شرط الساعة القديم.",
                f"الساعة {late_time} مناسبة، احجزها.",
                "هو الحجز اتعمل يوم كام والساعة كام؟",
                f"تمام، ومتغيروش للساعة {early_time} حتى لو كانت فاضية.",
            ],
            "Latest date/time constraint should replace stale flow constraints; final exact selection is the only booking write.",
        )

    raise KeyError(name)


def _run_case(engine, slug: str, name: str) -> dict[str, object]:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    result: dict[str, object] = {"name": name, "execution_error": None, "turns": []}
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise RuntimeError("Workspace not found")
        patient, messages, purpose = _setup_case(name, db, workspace)
        if not 5 <= len(messages) <= 10:
            raise RuntimeError(f"Conversation {name} has {len(messages)} turns; expected 5-10")
        result["purpose"] = purpose
        result["patient_id"] = str(patient.id)
        result["state_before"] = {
            "appointments": _appointment_snapshot(db, workspace, patient),
            "packages": _package_snapshot(db, workspace, patient),
        }

        conversation_id: UUID | None = None
        turns: list[dict[str, object]] = []
        for message in messages:
            response, duration_ms = _send(db, workspace, patient, message, conversation_id)
            conversation_id = response.conversation_id
            turns.append(
                {
                    "customer": message,
                    "assistant": response.reply,
                    "model": response.model,
                    "duration_ms": duration_ms,
                    "handoff_required": response.handoff_required,
                    "agent_paused": response.agent_paused,
                }
            )
            if response.agent_paused:
                # Preserve the real safety behavior; remaining turns would not be answered.
                break
        result["turns"] = turns
        result["observed_actions"] = _actions_for_conversation(db, workspace, conversation_id)
        result["state_after"] = {
            "appointments": _appointment_snapshot(db, workspace, patient),
            "packages": _package_snapshot(db, workspace, patient),
        }
        if conversation_id is not None:
            conversation = db.scalar(
                select(Conversation).where(
                    Conversation.workspace_id == workspace.id,
                    Conversation.id == conversation_id,
                )
            )
            result["conversation_owner_after"] = conversation.owner_type if conversation else None
    except Exception as exc:  # noqa: BLE001
        result["execution_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
    return result


def main() -> int:
    args = _args()
    if str(settings.environment or "").strip().lower() == "production":
        raise SystemExit("Refusing to run extended conversation review in production.")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    results: list[dict[str, object]] = []
    try:
        for index, name in enumerate(CASES, start=1):
            print(f"[{index:02d}/{len(CASES)}] {name}", flush=True)
            result = _run_case(engine, args.workspace_slug, name)
            results.append(result)
            error = result.get("execution_error")
            print("  -> transcript captured" if not error else f"  -> execution error: {error}", flush=True)
    finally:
        engine.dispose()

    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "workspace_slug": args.workspace_slug,
        "conversation_count": len(results),
        "quality_scoring": "manual_semantic_transcript_review_only",
        "automatic_pass_fail": False,
        "database_writes_persisted": False,
        "whatsapp_or_n8n_used": False,
        "customer_turn_range": [5, 10],
        "results": results,
    }
    path = Path(args.report)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {path}", flush=True)
    return 1 if any(item.get("execution_error") for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
