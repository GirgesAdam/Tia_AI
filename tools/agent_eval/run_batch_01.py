from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tools.agent_eval.harness import (
    ScenarioResult,
    active_branch_id,
    aggregate_tokens,
    assert_demo_only,
    batch_token_summary,
    booking_context,
    classify_issue,
    default_evaluation,
    find_patient,
    jsonable,
    local_slot,
    money,
    package_patient,
    seed_appointment,
    send_turn,
    service_by_slug,
    state_snapshot,
    write_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--output-dir", default="backend/eval_results")
    parser.add_argument("--git-sha", default=os.getenv("GITHUB_SHA") or "unknown")
    return parser.parse_args()


def require_explicit_demo_eval() -> None:
    if os.getenv("TIA_AGENT_EVAL_CONFIRM_DEMO") != "1":
        raise RuntimeError(
            "Set TIA_AGENT_EVAL_CONFIRM_DEMO=1 to run the live Demo evaluation."
        )


def quiet_patient(db: Session, workspace: Workspace) -> Patient:
    now = datetime.now(UTC)
    patient = db.scalar(
        select(Patient)
        .where(
            Patient.workspace_id == workspace.id,
            Patient.status != "blocked",
            ~select(Appointment.id)
            .where(
                Appointment.workspace_id == workspace.id,
                Appointment.patient_id == Patient.id,
                Appointment.start_at >= now,
                Appointment.status.in_(("pending", "confirmed")),
            )
            .exists(),
        )
        .order_by(Patient.created_at.asc())
        .limit(1)
    )
    return patient or find_patient(db, workspace)


def doctor_name(row: dict) -> str:
    return str(row.get("name") or row.get("display_name") or "الدكتور")


def branch_name(catalog: dict, branch_id: str) -> str:
    for row in catalog.get("branches", []):
        if isinstance(row, dict) and str(row.get("id")) == branch_id:
            return str(row.get("name") or "العيادة")
    return "العيادة"


def alternate_slot(db: Session, workspace: Workspace, context):
    _, service, doctor, branch_id, _, available = context
    first = available.slots[0]
    for slot in available.slots[1:]:
        if slot.start_at != first.start_at:
            return slot, available

    adapter = get_clinic_adapter(db=db, workspace=workspace)
    start_day = (
        first.start_at.astimezone(ZoneInfo(available.timezone)).date()
        + timedelta(days=1)
    )
    for offset in range(35):
        extra = adapter.get_availability(
            AvailabilityRequest(
                branch_id=branch_id,
                service_id=str(service["id"]),
                booking_date=start_day + timedelta(days=offset),
                doctor_id=str(doctor["id"]),
            )
        )
        if extra.slots:
            return extra.slots[0], extra
    raise RuntimeError("No alternate slot found.")


def context_with_two_doctors(db: Session, workspace: Workspace):
    catalog = booking_context(db, workspace)[0]
    branch_id = active_branch_id(catalog)
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    today = datetime.now(UTC).date()
    doctors = [
        row
        for row in catalog.get("doctors", [])
        if isinstance(row, dict) and row.get("id")
    ]

    for service in [
        row
        for row in catalog.get("services", [])
        if isinstance(row, dict)
        and row.get("id")
        and not row.get("requires_laser_device")
    ]:
        compatible = [
            doctor
            for doctor in doctors
            if str(service["id"])
            in {str(value) for value in (doctor.get("service_ids") or [])}
        ]
        found = []
        for doctor in compatible:
            scheduled = {
                str(value)
                for value in (
                    doctor.get("scheduled_branch_ids")
                    or doctor.get("branch_ids")
                    or []
                )
                if value
            }
            if scheduled and branch_id not in scheduled:
                continue
            for offset in range(1, 22):
                day = today + timedelta(days=offset)
                available = adapter.get_availability(
                    AvailabilityRequest(
                        branch_id=branch_id,
                        service_id=str(service["id"]),
                        booking_date=day,
                        doctor_id=str(doctor["id"]),
                    )
                )
                if available.slots:
                    found.append((doctor, day, available))
                    break
            if len(found) == 2:
                return catalog, service, branch_id, found[0], found[1]
    raise RuntimeError("No demo service with two bookable doctors found.")


def created_appointments(before: dict, after: dict) -> list[dict]:
    known = {row["id"] for row in before["appointments"]}
    return [
        row
        for row in after["appointments"]
        if row["id"] not in known
    ]


def run_messages(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    scenario_id: str,
    messages: list[str],
):
    turns = []
    conversation_id = None
    for idx, message in enumerate(messages, start=1):
        response, turn = send_turn(
            db,
            workspace,
            patient,
            scenario_id,
            idx,
            message,
            conversation_id,
        )
        conversation_id = response.conversation_id
        turns.append(turn)
    return turns


def case_price(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    service = service_by_slug(db, workspace, "prp-skin")
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "service_price_prp",
        ["جلسة PRP للبشرة بكام؟"],
    )
    after = state_snapshot(db, workspace, patient)
    expected = money(service.price_minor)
    grounded = expected in (turns[-1].agent_response or "").replace(",", "")
    issues = classify_issue(
        grounded,
        severity="P1",
        title="Incorrect or missing PRP price",
        detail=f"DB price is {expected} EGP.",
    )
    return (
        "service_price_prp",
        "pricing",
        "Verified current PRP skin price.",
        turns,
        before,
        after,
        {
            "expected_price_egp": expected,
            "reply_contains_current_price": grounded,
        },
        default_evaluation(grounding_ok=grounded),
        issues,
    )


def case_ambiguous_laser(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    context = booking_context(
        db,
        workspace,
        service_slug="laser-hair-removal-full-body-women",
    )
    catalog, service, doctor, branch_id, _, available = context
    date_text, _ = local_slot(available, available.slots[0])
    before = state_snapshot(db, workspace, patient)
    messages = [
        "عايزه احجز ليزر",
        "فول بادي",
        "برايم ليز",
        f"ممكن يوم {date_text} بالليل؟",
    ]
    turns = run_messages(
        db,
        workspace,
        patient,
        "booking_ambiguous_laser",
        messages,
    )
    after = state_snapshot(db, workspace, patient)
    no_write = len(created_appointments(before, after)) == 0
    issues = classify_issue(
        no_write,
        severity="P1",
        title="Ambiguous laser request caused a booking",
        detail="No exact slot was authorized.",
    )
    return (
        "booking_ambiguous_laser",
        "booking",
        "Progressively clarify ambiguous laser booking without assumptions.",
        turns,
        before,
        after,
        {
            "service": service["name"],
            "branch": branch_name(catalog, branch_id),
            "candidate_doctor": doctor_name(doctor),
            "no_booking_without_exact_slot": no_write,
        },
        default_evaluation(action_ok=no_write, db_ok=no_write),
        issues,
    )


def case_full_booking(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    context = booking_context(
        db,
        workspace,
        service_slug="hydrafacial",
    )
    catalog, service, doctor, branch_id, _, available = context
    date_text, time_text = local_slot(available, available.slots[0])
    before = state_snapshot(db, workspace, patient)
    messages = [
        f"عايزه احجز {service['name']}",
        f"في {branch_name(catalog, branch_id)}",
        f"مع دكتورة {doctor_name(doctor)}",
        f"يوم {date_text} الساعة {time_text}",
        "تمام احجزي",
    ]
    turns = run_messages(
        db,
        workspace,
        patient,
        "full_booking",
        messages,
    )
    after = state_snapshot(db, workspace, patient)
    created = created_appointments(before, after)
    ok = (
        len(created) == 1
        and created[0]["service_id"] == str(service["id"])
        and created[0]["doctor_id"] == str(doctor["id"])
        and created[0]["branch_id"] == branch_id
    )
    issues = classify_issue(
        ok,
        severity="P1",
        title="Full booking final state incorrect",
        detail=f"Expected exactly one grounded appointment, got {len(created)}.",
    )
    return (
        "full_booking",
        "booking",
        "Complete service→branch→doctor→slot→booking flow.",
        turns,
        before,
        after,
        {
            "created_appointments": created,
            "exactly_one_correct_booking": ok,
        },
        default_evaluation(action_ok=ok, db_ok=ok),
        issues,
    )


def case_unavailable(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    context = booking_context(
        db,
        workspace,
        service_slug="hydrafacial",
    )
    _, service, doctor, _, _, available = context
    date_text, _ = local_slot(available, available.slots[0])
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "unavailable_time",
        [
            (
                f"عايزه احجز {service['name']} مع {doctor_name(doctor)} "
                f"يوم {date_text} الساعة 03:17"
            )
        ],
    )
    after = state_snapshot(db, workspace, patient)
    ok = len(created_appointments(before, after)) == 0
    issues = classify_issue(
        ok,
        severity="P1",
        title="Unavailable time was booked",
        detail="03:17 should not be silently rounded or invented.",
    )
    return (
        "unavailable_time",
        "availability",
        "Reject unavailable time and present grounded alternatives.",
        turns,
        before,
        after,
        {"no_invalid_booking": ok},
        default_evaluation(action_ok=ok, db_ok=ok),
        issues,
    )


def case_doctor_preference(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    _, service, _, first, _ = context_with_two_doctors(db, workspace)
    doctor, _, available = first
    date_text, _ = local_slot(available, available.slots[0])
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "doctor_preference",
        [
            f"عايزة {service['name']} مع {doctor_name(doctor)} بس",
            f"ممكن يوم {date_text}؟",
        ],
    )
    after = state_snapshot(db, workspace, patient)
    created = created_appointments(before, after)
    correct_doctor = all(
        row["doctor_id"] == str(doctor["id"])
        for row in created
    )
    issues = classify_issue(
        correct_doctor,
        severity="P1",
        title="Doctor preference silently substituted",
        detail="Any write must preserve the requested doctor.",
    )
    return (
        "doctor_preference",
        "booking",
        "Preserve explicit doctor preference and avoid silent substitution.",
        turns,
        before,
        after,
        {
            "requested_doctor": doctor_name(doctor),
            "writes_preserve_doctor": correct_doctor,
            "created": created,
        },
        default_evaluation(
            action_ok=correct_doctor if created else None,
            db_ok=correct_doctor,
        ),
        issues,
    )


def case_change_mind(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    _, service, _, first, second = context_with_two_doctors(db, workspace)
    doctor1, _, available1 = first
    doctor2, _, available2 = second
    date1, _ = local_slot(available1, available1.slots[0])
    date2, time2 = local_slot(available2, available2.slots[0])
    before = state_snapshot(db, workspace, patient)
    messages = [
        f"عايزة احجز {service['name']} يوم {date1} مع {doctor_name(doctor1)}",
        f"لا معلش يوم {date2} أحسن",
        f"لا خليها مع {doctor_name(doctor2)} الساعة {time2}",
    ]
    turns = run_messages(
        db,
        workspace,
        patient,
        "change_mind_booking",
        messages,
    )
    after = state_snapshot(db, workspace, patient)
    created = created_appointments(before, after)
    latest_wins = all(
        row["doctor_id"] == str(doctor2["id"])
        for row in created
    )
    issues = classify_issue(
        latest_wins,
        severity="P1",
        title="Stale booking state won over latest intent",
        detail="Any created appointment must use the second doctor.",
    )
    return (
        "change_mind_booking",
        "continuity",
        "Latest date/doctor intent must replace stale booking state.",
        turns,
        before,
        after,
        {
            "created": created,
            "latest_doctor_wins": latest_wins,
        },
        default_evaluation(
            action_ok=latest_wins if created else None,
            db_ok=latest_wins,
            continuity_ok=latest_wins,
        ),
        issues,
    )


def case_reschedule(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    context = booking_context(
        db,
        workspace,
        service_slug="hydrafacial",
    )
    existing = seed_appointment(db, workspace, patient, context)
    before = state_snapshot(db, workspace, patient)
    slot, available = alternate_slot(db, workspace, context)
    date_text, time_text = local_slot(available, slot)
    turns = run_messages(
        db,
        workspace,
        patient,
        "reschedule_existing",
        [
            "ممكن أغير ميعادي؟",
            f"خليه يوم {date_text} الساعة {time_text}",
        ],
    )
    after = state_snapshot(db, workspace, patient)
    rows = [
        row
        for row in after["appointments"]
        if row["id"] == str(existing.id)
    ]
    duplicates = len(created_appointments(before, after))
    target_iso = slot.start_at.isoformat()
    ok = (
        bool(rows)
        and rows[0]["start_at"] == target_iso
        and duplicates == 0
    )
    issues = classify_issue(
        ok,
        severity="P1",
        title="Reschedule state incorrect",
        detail=(
            f"Expected same appointment moved to {target_iso} "
            "with no duplicate."
        ),
    )
    return (
        "reschedule_existing",
        "reschedule",
        "Verified read then reschedule the real upcoming appointment.",
        turns,
        before,
        after,
        {
            "appointment_id": str(existing.id),
            "target_start": target_iso,
            "same_row_rescheduled": ok,
            "duplicate_count": duplicates,
        },
        default_evaluation(action_ok=ok, db_ok=ok),
        issues,
    )


def case_cancel(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    existing = seed_appointment(
        db,
        workspace,
        patient,
        booking_context(
            db,
            workspace,
            service_slug="hydrafacial",
        ),
    )
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "cancel_existing",
        ["عايزة ألغي ميعادي", "ايوه الغيه"],
    )
    after = state_snapshot(db, workspace, patient)
    row = next(
        (
            item
            for item in after["appointments"]
            if item["id"] == str(existing.id)
        ),
        None,
    )
    ok = (
        row is not None
        and row["status"] == "cancelled"
        and len(created_appointments(before, after)) == 0
    )
    issues = classify_issue(
        ok,
        severity="P1",
        title="Cancellation final state incorrect",
        detail=(
            "The selected appointment should be cancelled "
            "without a duplicate write."
        ),
    )
    return (
        "cancel_existing",
        "cancellation",
        "Resolve and cancel the customer's real upcoming appointment.",
        turns,
        before,
        after,
        {
            "appointment_id": str(existing.id),
            "final_status": row["status"] if row else None,
            "correct": ok,
        },
        default_evaluation(action_ok=ok, db_ok=ok),
        issues,
    )


def case_package_remaining(db: Session, workspace: Workspace):
    patient, package = package_patient(db, workspace)
    service = db.get(Service, package.service_id)
    before = state_snapshot(db, workspace, patient)
    package_before = next(
        row
        for row in before["packages"]
        if row["id"] == str(package.id)
    )
    turns = run_messages(
        db,
        workspace,
        patient,
        "package_remaining",
        ["فاضلي كام جلسة؟"],
    )
    after = state_snapshot(db, workspace, patient)
    remaining = package_before["remaining"]
    grounded = (
        remaining is None
        or str(remaining) in (turns[-1].agent_response or "")
    )
    issues = classify_issue(
        grounded,
        severity="P1",
        title="Package remaining count not grounded",
        detail=(
            f"Canonical remaining={remaining} for "
            f"{service.name if service else package.name}."
        ),
    )
    return (
        "package_remaining",
        "packages",
        "Read actual remaining package sessions.",
        turns,
        before,
        after,
        {
            "package_id": str(package.id),
            "remaining": remaining,
            "reply_contains_remaining": grounded,
        },
        default_evaluation(grounding_ok=grounded),
        issues,
    )


def case_package_other_service(db: Session, workspace: Workspace):
    prp = service_by_slug(db, workspace, "prp-skin")
    patient, package = package_patient(
        db,
        workspace,
        exclude_service_id=prp.id,
    )
    context = booking_context(
        db,
        workspace,
        service_slug="prp-skin",
    )
    _, service, doctor, _, _, available = context
    date_text, time_text = local_slot(available, available.slots[0])
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "package_holder_other_service",
        [
            f"أنا عندي باكيدج بس عايزة أحجز {service['name']}",
            f"مع {doctor_name(doctor)} يوم {date_text} الساعة {time_text}",
        ],
    )
    after = state_snapshot(db, workspace, patient)
    created = created_appointments(before, after)
    before_package = next(
        (row for row in before["packages"] if row["id"] == str(package.id)),
        None,
    )
    after_package = next(
        (row for row in after["packages"] if row["id"] == str(package.id)),
        None,
    )
    untouched = before_package == after_package
    correct = (
        all(
            row["service_id"] == str(prp.id)
            and row["patient_package_id"] is None
            for row in created
        )
        and untouched
    )
    issues = classify_issue(
        correct,
        severity="P0",
        title="Unrelated package was consumed/corrupted",
        detail=(
            "PRP request must not consume the existing "
            "different-service package."
        ),
    )
    return (
        "package_holder_other_service",
        "packages",
        "Book a different service without consuming unrelated entitlement.",
        turns,
        before,
        after,
        {
            "created": created,
            "unrelated_package_unchanged": untouched,
            "correct": correct,
        },
        default_evaluation(
            action_ok=correct if created else None,
            db_ok=correct,
        ),
        issues,
    )


def case_device_price(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    service = service_by_slug(
        db,
        workspace,
        "laser-hair-removal-underarm",
    )
    candela = db.execute(
        text(
            "SELECT device_name, price_minor "
            "FROM service_device_prices "
            "WHERE workspace_id=:workspace_id "
            "AND service_id=:service_id "
            "AND device_key='candela_gentle'"
        ),
        {
            "workspace_id": workspace.id,
            "service_id": service.id,
        },
    ).mappings().first()
    if candela is None:
        raise RuntimeError(
            "Demo underarm service has no Candela price."
        )
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "device_specific_price",
        ["ليزر الإبط بكام؟", "على كانديلا؟"],
    )
    after = state_snapshot(db, workspace, patient)
    expected = money(int(candela["price_minor"]))
    grounded = expected in (turns[-1].agent_response or "").replace(",", "")
    issues = classify_issue(
        grounded,
        severity="P1",
        title="Device-specific price incorrect",
        detail=f"Candela canonical price is {expected} EGP.",
    )
    return (
        "device_specific_price",
        "pricing",
        "Require and retain device context before quoting laser price.",
        turns,
        before,
        after,
        {
            "device": str(candela["device_name"]),
            "expected_price_egp": expected,
            "reply_contains_price": grounded,
        },
        default_evaluation(
            grounding_ok=grounded,
            continuity_ok=grounded,
        ),
        issues,
    )


def case_multi_question(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    context = booking_context(
        db,
        workspace,
        service_slug="prp-skin",
    )
    _, service, _, _, _, available = context
    date_text, _ = local_slot(available, available.slots[0])
    db_service = service_by_slug(db, workspace, "prp-skin")
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "multi_question",
        [
            (
                f"جلسة {service['name']} بكام "
                f"وممكن احجز يوم {date_text}؟"
            )
        ],
    )
    after = state_snapshot(db, workspace, patient)
    reply = turns[-1].agent_response or ""
    price_ok = money(db_service.price_minor) in reply.replace(",", "")
    booking_intent_retained = (
        bool(turns[-1].verified_reads)
        or "موعد" in reply
        or "متاح" in reply
    )
    ok = price_ok and booking_intent_retained
    issues = classify_issue(
        ok,
        severity="P1",
        title="Multi-question request lost a component",
        detail=(
            "Reply should cover price and continue "
            "booking/availability intent."
        ),
    )
    return (
        "multi_question",
        "compound",
        "Answer price and retain booking intent from one message.",
        turns,
        before,
        after,
        {
            "price_grounded": price_ok,
            "booking_intent_retained": booking_intent_retained,
        },
        default_evaluation(
            grounding_ok=price_ok,
            continuity_ok=booking_intent_retained,
        ),
        issues,
    )


def case_context_followup(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    _, service, _, first, second = context_with_two_doctors(db, workspace)
    doctor1, _, available1 = first
    doctor2, _, _ = second
    date_text, _ = local_slot(available1, available1.slots[0])
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "contextual_followup",
        [
            f"مين الدكاترة اللي بيعملوا {service['name']} ومتاحين قريب؟",
            "والدكتورة التانية؟",
        ],
    )
    after = state_snapshot(db, workspace, patient)
    second_reply = turns[-1].agent_response or ""
    understood = bool(second_reply.strip()) and not turns[-1].errors
    issues = classify_issue(
        understood,
        severity="P1",
        title="Contextual short follow-up lost referent",
        detail=(
            "The prior verified doctor set included "
            f"{doctor_name(doctor1)} and {doctor_name(doctor2)}."
        ),
    )
    return (
        "contextual_followup",
        "continuity",
        "Resolve a short follow-up from verified conversation context.",
        turns,
        before,
        after,
        {
            "service": service["name"],
            "doctor_set": [
                doctor_name(doctor1),
                doctor_name(doctor2),
            ],
            "second_reply_nonempty": understood,
            "sample_date": date_text,
        },
        default_evaluation(continuity_ok=understood),
        issues,
    )


def case_unknown_fact(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "unknown_clinic_fact",
        ["فيه باركينج مجاني مخصوص للعيادة تحت المبنى؟"],
    )
    after = state_snapshot(db, workspace, patient)
    reply = (turns[-1].agent_response or "").casefold()
    unsafe_assertion = any(
        token in reply
        for token in (
            "ايوه فيه",
            "أيوة فيه",
            "نعم يوجد",
            "متوفر باركينج مجاني",
        )
    )
    ok = not unsafe_assertion
    issues = classify_issue(
        ok,
        severity="P1",
        title="Unsupported clinic fact hallucinated",
        detail=(
            "Parking availability is not a canonical known fact "
            "for this scenario."
        ),
    )
    return (
        "unknown_clinic_fact",
        "grounding",
        "Do not invent a clinic-specific fact absent from knowledge.",
        turns,
        before,
        after,
        {"no_positive_parking_hallucination": ok},
        default_evaluation(grounding_ok=ok),
        issues,
    )


def case_handoff(db: Session, workspace: Workspace):
    patient = quiet_patient(db, workspace)
    before = state_snapshot(db, workspace, patient)
    turns = run_messages(
        db,
        workspace,
        patient,
        "human_handoff",
        [
            "ممكن أكلم الريسبشن؟",
            "أنا موجودة، حد يرد عليا لو سمحت",
        ],
    )
    after = state_snapshot(db, workspace, patient)
    first_handoff = turns[0].handoff_state is not None
    second_paused = (
        turns[1].runtime_state.get("agent_paused") is True
        and turns[1].agent_response is None
    )
    ok = first_handoff and second_paused
    issues = classify_issue(
        ok,
        severity="P1",
        title="Human handoff ownership behavior incorrect",
        detail=(
            "Expected handoff then no AI reply "
            "on the next inbound turn."
        ),
    )
    return (
        "human_handoff",
        "handoff",
        "Explicit reception request transfers ownership and pauses AI.",
        turns,
        before,
        after,
        {
            "handoff_created": first_handoff,
            "second_turn_ai_paused": second_paused,
        },
        default_evaluation(handoff_ok=ok, db_ok=ok),
        issues,
    )


CASES = [
    case_price,
    case_ambiguous_laser,
    case_full_booking,
    case_unavailable,
    case_doctor_preference,
    case_change_mind,
    case_reschedule,
    case_cancel,
    case_package_remaining,
    case_package_other_service,
    case_device_price,
    case_multi_question,
    case_context_followup,
    case_unknown_fact,
    case_handoff,
]


def run_case(engine, slug: str, case_fn) -> ScenarioResult:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        workspace = db.scalar(
            select(Workspace).where(Workspace.slug == slug)
        )
        if workspace is None:
            raise RuntimeError("Workspace not found.")
        assert_demo_only(workspace)
        case = case_fn(db, workspace)
        (
            scenario_id,
            category,
            purpose,
            turns,
            before,
            after,
            verification,
            evaluation,
            issues,
        ) = case
        return ScenarioResult(
            id=scenario_id,
            category=category,
            purpose=purpose,
            turns=turns,
            state_before=before,
            state_after=after,
            db_verification=verification,
            evaluation=evaluation,
            issues=issues,
            token_usage=aggregate_tokens(turns),
        )
    except Exception as exc:  # noqa: BLE001
        name = case_fn.__name__.removeprefix("case_")
        return ScenarioResult(
            id=name,
            category="unknown",
            purpose="Execution failed before evaluation completed.",
            turns=[],
            state_before={},
            state_after={},
            db_verification={},
            evaluation=default_evaluation(
                db_ok=False,
                grounding_ok=False,
            ),
            issues=[
                {
                    "severity": "P1",
                    "title": "Scenario execution error",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            ],
            token_usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
                "metadata_missing_calls": 0,
            },
            execution_error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        connection.close()


def summarize(results: list[ScenarioResult]) -> dict:
    pcounts = {f"P{i}": 0 for i in range(4)}
    for row in results:
        for issue in row.issues:
            if issue["severity"] in pcounts:
                pcounts[issue["severity"]] += 1

    fully_correct = sum(
        not row.issues and row.execution_error is None
        for row in results
    )
    minor = sum(
        1
        for row in results
        if row.execution_error is None
        and bool(row.issues)
        and all(
            issue["severity"] in {"P2", "P3"}
            for issue in row.issues
        )
    )
    failed = len(results) - fully_correct - minor
    tokens = batch_token_summary(results)
    median = float(tokens.get("median_tokens_per_conversation") or 0)

    for row in results:
        total = row.token_usage["total_tokens"]
        if median and total > median * 2.5:
            row.evaluation["token_efficiency"] = "VERY_HIGH"
        elif median and total > median * 1.5:
            row.evaluation["token_efficiency"] = "HIGH"

    return {
        "scenarios_run": len(results),
        "fully_correct": fully_correct,
        "acceptable_with_minor_issues": minor,
        "failed": failed,
        **pcounts,
        "tokens": tokens,
        "successful_bookings": sum(
            row.id in {
                "full_booking",
                "package_holder_other_service",
            }
            and row.evaluation["db_final_state"] == "CORRECT"
            for row in results
        ),
        "reschedules": sum(
            row.id == "reschedule_existing"
            and row.evaluation["db_final_state"] == "CORRECT"
            for row in results
        ),
        "cancellations": sum(
            row.id == "cancel_existing"
            and row.evaluation["db_final_state"] == "CORRECT"
            for row in results
        ),
        "handoffs": sum(
            row.id == "human_handoff"
            and row.evaluation["handoff_behavior"] == "CORRECT"
            for row in results
        ),
        "grounding_failures": sum(
            row.evaluation["grounding"] == "ISSUE"
            for row in results
        ),
        "continuity_failures": sum(
            row.evaluation["continuity"] == "ISSUE"
            for row in results
        ),
    }


def main() -> int:
    ns = parse_args()
    require_explicit_demo_eval()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    with Session(engine) as db:
        workspace = db.scalar(
            select(Workspace).where(
                Workspace.slug == ns.workspace_slug
            )
        )
        if workspace is None:
            raise RuntimeError("Demo workspace not found.")
        assert_demo_only(workspace)
        policy_check = {
            "is_demo": True,
            "external_side_effects_blocked": True,
            "workspace_id": str(workspace.id),
        }

    results: list[ScenarioResult] = []
    for case_fn in CASES:
        row = run_case(engine, ns.workspace_slug, case_fn)
        results.append(row)
        if any(
            issue["severity"] == "P0"
            for issue in row.issues
        ):
            break

    summary = summarize(results)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(ns.output_dir)
    payload = {
        "run_metadata": {
            "batch": 1,
            "git_sha": ns.git_sha,
            "workspace": ns.workspace_slug,
            "started_from_main": True,
            "model_config": settings.openai_model,
            "generated_at": datetime.now(UTC).isoformat(),
            **policy_check,
        },
        "scenario_results": [
            jsonable(row)
            for row in results
        ],
        "batch_summary": summary,
    }
    json_path = output_dir / f"batch_01_{timestamp}.json"
    md_path = output_dir / f"batch_01_{timestamp}.md"
    write_reports(payload, json_path, md_path)
    print(f"JSON_RESULT={json_path}")
    print(f"MD_RESULT={md_path}")
    print(f"SCENARIOS_RUN={len(results)}")
    print(
        f"P0={summary['P0']} P1={summary['P1']} "
        f"P2={summary['P2']} P3={summary['P3']}"
    )
    print(
        f"TOTAL_TOKENS={summary['tokens']['total_tokens']}"
    )
    missing = sum(
        row.token_usage.get("metadata_missing_calls", 0)
        for row in results
    )
    if missing:
        print(
            f"WARNING_USAGE_METADATA_MISSING_CALLS={missing}"
        )
    return 2 if summary["P0"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
