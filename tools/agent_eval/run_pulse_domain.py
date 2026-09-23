from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.agents.clinic_grounding import build_clinic_catalog
from app.integrations.clinic.base import AvailabilityRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.payment_transaction import PaymentTransaction
from app.models.pulse_billing import (
    AppointmentPulseSettlement,
    PatientPulsePack,
    PulsePackOffer,
    PulseUsage,
)
from app.models.workspace import Workspace
from app.services.pulse_billing import (
    list_patient_pulse_balances,
    list_patient_pulse_packs,
    list_pulse_billing_settings,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from tools.agent_eval.harness import (
    ScenarioResult,
    active_branch_id,
    aggregate_tokens,
    assert_demo_only,
    batch_token_summary,
    classify_issue,
    default_evaluation,
    jsonable,
    send_turn,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument("--output-dir", default="backend/eval_results")
    parser.add_argument("--git-sha", default=os.getenv("GITHUB_SHA") or "unknown")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only an exact case function suffix (the text after case_); may be repeated.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print a compact qualitative result instead of the full eval payload.",
    )
    return parser.parse_args()


def require_explicit_demo_eval() -> None:
    if os.getenv("TIA_AGENT_EVAL_CONFIRM_DEMO") != "1":
        raise RuntimeError("Set TIA_AGENT_EVAL_CONFIRM_DEMO=1 to run the live Demo evaluation.")


def _patient_with_pulse_balance(db: Session, workspace: Workspace) -> Patient:
    candidate_ids = list(
        db.scalars(
            select(PatientPulsePack.patient_id)
            .where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.status == "active",
            )
            .distinct()
            .limit(100)
        )
    )
    for patient_id in candidate_ids:
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == workspace.id,
                Patient.id == patient_id,
                Patient.status != "blocked",
            )
        )
        if patient is None:
            continue
        balances = list_patient_pulse_balances(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
        )
        if any(row.pulses_remaining > 0 for row in balances):
            return patient
    raise RuntimeError("EVAL_INFRA_ERROR: demo has no patient with active Pulse balance")


def _active_offer(db: Session, workspace: Workspace) -> PulsePackOffer:
    row = db.scalar(
        select(PulsePackOffer)
        .where(
            PulsePackOffer.workspace_id == workspace.id,
            PulsePackOffer.is_active.is_(True),
        )
        .order_by(PulsePackOffer.device_key, PulsePackOffer.pulses_count)
        .limit(1)
    )
    if row is None:
        raise RuntimeError("EVAL_INFRA_ERROR: demo has no active Pulse-pack offer")
    return row


def _active_patient(db: Session, workspace: Workspace) -> Patient:
    row = db.scalar(
        select(Patient)
        .where(
            Patient.workspace_id == workspace.id,
            Patient.status != "blocked",
        )
        .order_by(Patient.created_at)
        .limit(1)
    )
    if row is None:
        raise RuntimeError("EVAL_INFRA_ERROR: demo has no active patient")
    return row


def _patient_without_device_balance(
    db: Session,
    workspace: Workspace,
    *,
    device_key: str,
) -> Patient:
    patients = list(
        db.scalars(
            select(Patient)
            .where(
                Patient.workspace_id == workspace.id,
                Patient.status != "blocked",
            )
            .order_by(Patient.created_at)
            .limit(100)
        )
    )
    for patient in patients:
        balances = list_patient_pulse_balances(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
        )
        matching = [
            row for row in balances
            if row.device_key == device_key and row.pulses_remaining > 0
        ]
        if not matching:
            return patient
    raise RuntimeError(
        f"EVAL_INFRA_ERROR: every demo patient already has Pulse balance for {device_key}"
    )


def _laser_booking_fixture(
    db: Session,
    workspace: Workspace,
    *,
    offer: PulsePackOffer,
):
    catalog = build_clinic_catalog(db, workspace)
    branch_id = active_branch_id(catalog)
    services = [
        row
        for row in catalog.get("services", [])
        if isinstance(row, dict)
        and row.get("id")
        and any(
            isinstance(device, dict)
            and device.get("device_key") == offer.device_key
            and device.get("configured") is True
            for device in (row.get("laser_devices") or [])
        )
    ]
    doctors = [
        row
        for row in catalog.get("doctors", [])
        if isinstance(row, dict) and row.get("id")
    ]
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    today = datetime.now(UTC).date()

    for service in services:
        service_id = str(service["id"])
        for doctor in doctors:
            if service_id not in {
                str(value) for value in (doctor.get("service_ids") or [])
            }:
                continue
            branch_ids = {
                str(value) for value in (doctor.get("branch_ids") or []) if value
            }
            if branch_ids and branch_id not in branch_ids:
                continue
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
            for offset in range(1, 36):
                booking_date = today + timedelta(days=offset)
                available = adapter.get_availability(
                    AvailabilityRequest(
                        branch_id=branch_id,
                        service_id=service_id,
                        booking_date=booking_date,
                        doctor_id=str(doctor["id"]),
                        laser_device_key=offer.device_key,
                    )
                )
                if available.slots:
                    return catalog, service, doctor, available, available.slots[0]
    raise RuntimeError(
        "EVAL_INFRA_ERROR: no bookable laser slot matches an active Pulse-pack device"
    )


def _standard_booking_fixture(
    db: Session,
    workspace: Workspace,
):
    catalog = build_clinic_catalog(db, workspace)
    branch_id = active_branch_id(catalog)
    services = [
        row
        for row in catalog.get("services", [])
        if isinstance(row, dict)
        and row.get("id")
        and not bool(row.get("requires_laser_device"))
    ]
    doctors = [
        row
        for row in catalog.get("doctors", [])
        if isinstance(row, dict) and row.get("id")
    ]
    adapter = get_clinic_adapter(db=db, workspace=workspace)
    adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
    today = datetime.now(UTC).date()

    for service in services:
        service_id = str(service["id"])
        for doctor in doctors:
            if service_id not in {
                str(value) for value in (doctor.get("service_ids") or [])
            }:
                continue
            branch_ids = {
                str(value) for value in (doctor.get("branch_ids") or []) if value
            }
            if branch_ids and branch_id not in branch_ids:
                continue
            for offset in range(1, 36):
                booking_date = today + timedelta(days=offset)
                available = adapter.get_availability(
                    AvailabilityRequest(
                        branch_id=branch_id,
                        service_id=service_id,
                        booking_date=booking_date,
                        doctor_id=str(doctor["id"]),
                    )
                )
                if available.slots:
                    return catalog, service, doctor, available, available.slots[0]
    raise RuntimeError("EVAL_INFRA_ERROR: no bookable non-laser service found")


def _created_appointments(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    *,
    before_ids: set[str],
) -> list[Appointment]:
    rows = list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.workspace_id == workspace.id,
                Appointment.patient_id == patient.id,
            )
            .order_by(Appointment.created_at)
        )
    )
    return [row for row in rows if str(row.id) not in before_ids]


def _appointment_ids(
    db: Session,
    workspace: Workspace,
    patient: Patient,
) -> set[str]:
    return {
        str(value)
        for value in db.scalars(
            select(Appointment.id).where(
                Appointment.workspace_id == workspace.id,
                Appointment.patient_id == patient.id,
            )
        )
    }


def _pulse_pack_count(db: Session, workspace: Workspace, patient: Patient) -> int:
    return int(
        db.scalar(
            select(func.count(PatientPulsePack.id)).where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.patient_id == patient.id,
            )
        )
        or 0
    )


def _payment_count(db: Session, workspace: Workspace, patient: Patient) -> int:
    return int(
        db.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.workspace_id == workspace.id,
                PaymentTransaction.patient_id == patient.id,
            )
        )
        or 0
    )


def _active_offer_for_device(
    db: Session,
    workspace: Workspace,
    *,
    device_key: str,
) -> PulsePackOffer:
    row = db.scalar(
        select(PulsePackOffer)
        .where(
            PulsePackOffer.workspace_id == workspace.id,
            PulsePackOffer.device_key == device_key,
            PulsePackOffer.is_active.is_(True),
        )
        .order_by(PulsePackOffer.pulses_count)
        .limit(1)
    )
    if row is None:
        raise RuntimeError(
            f"EVAL_INFRA_ERROR: no active Pulse-pack offer for {device_key}"
        )
    return row


def _distinct_device_offers(
    db: Session,
    workspace: Workspace,
) -> tuple[PulsePackOffer, PulsePackOffer]:
    rows = list(
        db.scalars(
            select(PulsePackOffer)
            .where(
                PulsePackOffer.workspace_id == workspace.id,
                PulsePackOffer.is_active.is_(True),
            )
            .order_by(PulsePackOffer.device_key, PulsePackOffer.pulses_count)
        )
    )
    by_device: dict[str, PulsePackOffer] = {}
    for row in rows:
        by_device.setdefault(row.device_key, row)
    if len(by_device) < 2:
        raise RuntimeError("EVAL_INFRA_ERROR: demo needs active Pulse offers on two devices")
    values = list(by_device.values())
    return values[0], values[1]


def _device_balance(
    db: Session,
    workspace: Workspace,
    patient: Patient,
    *,
    device_key: str,
) -> int:
    return next(
        (
            int(row.pulses_remaining)
            for row in list_patient_pulse_balances(
                db,
                workspace_id=workspace.id,
                patient_id=patient.id,
            )
            if row.device_key == device_key
        ),
        0,
    )


def _appointment_pulse_artifacts(
    db: Session,
    workspace: Workspace,
    appointment: Appointment | None,
) -> dict[str, int]:
    if appointment is None:
        return {"usages": 0, "settlements": 0}
    usages = int(
        db.scalar(
            select(func.count(PulseUsage.id)).where(
                PulseUsage.workspace_id == workspace.id,
                PulseUsage.appointment_id == appointment.id,
            )
        )
        or 0
    )
    settlements = int(
        db.scalar(
            select(func.count(AppointmentPulseSettlement.id)).where(
                AppointmentPulseSettlement.workspace_id == workspace.id,
                AppointmentPulseSettlement.appointment_id == appointment.id,
            )
        )
        or 0
    )
    return {"usages": usages, "settlements": settlements}


def _result(
    *,
    scenario_id: str,
    purpose: str,
    turns,
    verification: dict,
    ok: bool,
    issue_title: str,
    issue_detail: str,
    action: bool = False,
) -> ScenarioResult:
    return ScenarioResult(
        id=scenario_id,
        category="pulses",
        purpose=purpose,
        turns=turns,
        state_before={},
        state_after={},
        db_verification=verification,
        evaluation=default_evaluation(
            db_ok=ok,
            action_ok=ok if action else None,
            grounding_ok=ok,
        ),
        issues=classify_issue(
            ok,
            severity="P1",
            title=issue_title,
            detail=issue_detail,
        ),
        token_usage=aggregate_tokens(turns),
    )


def case_balance(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _patient_with_pulse_balance(db, workspace)
    balances = list_patient_pulse_balances(
        db,
        workspace_id=workspace.id,
        patient_id=patient.id,
    )
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_balance",
        1,
        "معايا كام pulse متبقية؟",
        None,
    )
    reply = (turn.agent_response or "").replace(",", "")
    expected = [row.pulses_remaining for row in balances]
    grounded = (
        "pulse_balance" in turn.verified_reads
        and not turn.write_attempted
        and any(str(value) in reply for value in expected)
    )
    return _result(
        scenario_id="pulse_balance",
        purpose="Read canonical patient Pulse balance without a write.",
        turns=[turn],
        verification={
            "balances": [row.model_dump(mode="json") for row in balances],
            "verified_read": "pulse_balance" in turn.verified_reads,
            "write_attempted": turn.write_attempted,
        },
        ok=grounded,
        issue_title="Pulse balance answer was not canonically grounded",
        issue_detail=f"Expected one of remaining balances {expected} from pulse_balance read.",
    )


def case_owned_pack_remaining(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _patient_with_pulse_balance(db, workspace)
    packs = [
        row
        for row in list_patient_pulse_packs(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
            include_financials=False,
        )
        if row.effective_status == "active"
    ]
    if not packs:
        raise RuntimeError("EVAL_INFRA_ERROR: patient has no active Pulse pack")
    target = packs[0]
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_owned_pack_remaining",
        1,
        f"الباقة اللي عندي على {target.device_name} فاضل فيها كام Pulse؟",
        None,
    )
    reply = (turn.agent_response or "").replace(",", "")
    ok = (
        "pulse_packs" in turn.verified_reads
        and not turn.write_attempted
        and str(target.pulses_remaining) in reply
    )
    return _result(
        scenario_id="pulse_owned_pack_remaining",
        purpose="Read owned Pulse-pack usage/remaining facts without exposing the payment ledger.",
        turns=[turn],
        verification={
            "device": target.device_name,
            "pulses_purchased": target.pulses_purchased,
            "pulses_consumed": target.pulses_consumed,
            "pulses_remaining": target.pulses_remaining,
            "verified_reads": turn.verified_reads,
        },
        ok=ok,
        issue_title="Owned Pulse-pack remaining amount was not grounded",
        issue_detail="Expected pulse_packs read and canonical remaining Pulse count.",
    )


def case_offer_price(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _active_patient(db, workspace)
    offer = _active_offer(db, workspace)
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_offer_price",
        1,
        f"باقة {offer.pulses_count} pulse على {offer.device_name} بكام؟",
        None,
    )
    expected_price = f"{offer.price_minor / 100:g}"
    reply = (turn.agent_response or "").replace(",", "")
    ok = (
        "pulse_pack_offers" in turn.verified_reads
        and not turn.write_attempted
        and expected_price in reply
    )
    return _result(
        scenario_id="pulse_offer_price",
        purpose="Read the exact active Pulse-pack offer price.",
        turns=[turn],
        verification={
            "offer_id": str(offer.id),
            "device": offer.device_name,
            "pulses_count": offer.pulses_count,
            "price_minor": offer.price_minor,
            "verified_read": "pulse_pack_offers" in turn.verified_reads,
        },
        ok=ok,
        issue_title="Pulse-pack price was not grounded from the offer read",
        issue_detail=f"Expected verified offer price {expected_price} EGP.",
    )


def case_overage_price(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _active_patient(db, workspace)
    settings = [
        row
        for row in list_pulse_billing_settings(db, workspace_id=workspace.id)
        if row.overage_price_minor is not None
    ]
    if not settings:
        raise RuntimeError("EVAL_INFRA_ERROR: no configured Pulse overage price")
    row = settings[0]
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_overage_price",
        1,
        f"الـ pulse الزيادة على {row.device_name} سعرها كام؟",
        None,
    )
    expected_price = f"{int(row.overage_price_minor or 0) / 100:g}"
    reply = (turn.agent_response or "").replace(",", "")
    ok = (
        "pulse_billing_settings" in turn.verified_reads
        and not turn.write_attempted
        and expected_price in reply
    )
    return _result(
        scenario_id="pulse_overage_price",
        purpose="Read device-specific Pulse overage price from canonical settings.",
        turns=[turn],
        verification={
            "device": row.device_name,
            "overage_price_minor": row.overage_price_minor,
            "verified_read": "pulse_billing_settings" in turn.verified_reads,
        },
        ok=ok,
        issue_title="Pulse overage price was not grounded",
        issue_detail=f"Expected verified overage price {expected_price} EGP.",
    )


def case_counted_overage(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _active_patient(db, workspace)
    settings = [
        row
        for row in list_pulse_billing_settings(db, workspace_id=workspace.id)
        if row.overage_price_minor is not None
    ]
    if not settings:
        raise RuntimeError("EVAL_INFRA_ERROR: no configured Pulse overage price")
    row = settings[0]
    count = 1000
    expected_total_minor = count * int(row.overage_price_minor or 0)
    expected_total = f"{expected_total_minor / 100:g}"
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_counted_overage",
        1,
        f"لو احتجت {count} Pulse زيادة على {row.device_name} هتكلف كام؟",
        None,
    )
    reply = (turn.agent_response or "").replace(",", "")
    ok = (
        "pulse_billing_settings" in turn.verified_reads
        and "pulse_pack_offers" not in turn.verified_reads
        and not turn.write_attempted
        and expected_total in reply
    )
    return _result(
        scenario_id="pulse_counted_overage",
        purpose="Interpret an exact count of extra Pulses as overage and use deterministic unit-price math.",
        turns=[turn],
        verification={
            "device": row.device_name,
            "pulse_count": count,
            "overage_unit_price_minor": row.overage_price_minor,
            "expected_total_minor": expected_total_minor,
            "verified_reads": turn.verified_reads,
        },
        ok=ok,
        issue_title="Counted Pulse overage was confused with a Pulse-pack offer",
        issue_detail="Expected only pulse_billing_settings and deterministic overage total.",
    )



def case_purchase_without_payment(db: Session, workspace: Workspace) -> ScenarioResult:
    patient = _active_patient(db, workspace)
    offer = _active_offer(db, workspace)
    before_packs = int(
        db.scalar(
            select(func.count(PatientPulsePack.id)).where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.patient_id == patient.id,
            )
        )
        or 0
    )
    before_payments = int(
        db.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.workspace_id == workspace.id,
                PaymentTransaction.patient_id == patient.id,
            )
        )
        or 0
    )
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_pack_purchase",
        1,
        f"اشتريلي باقة {offer.pulses_count} pulse على {offer.device_name}",
        None,
    )
    after_packs = int(
        db.scalar(
            select(func.count(PatientPulsePack.id)).where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.patient_id == patient.id,
            )
        )
        or 0
    )
    after_payments = int(
        db.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.workspace_id == workspace.id,
                PaymentTransaction.patient_id == patient.id,
            )
        )
        or 0
    )
    created = list(
        db.scalars(
            select(PatientPulsePack)
            .where(
                PatientPulsePack.workspace_id == workspace.id,
                PatientPulsePack.patient_id == patient.id,
            )
            .order_by(PatientPulsePack.created_at.desc())
            .limit(1)
        )
    )
    latest = created[0] if created else None
    ok = (
        "pulse_pack_offers" in turn.verified_reads
        and turn.write_attempted
        and after_packs == before_packs + 1
        and after_payments == before_payments
        and latest is not None
        and latest.pulse_pack_offer_id == offer.id
        and latest.purchase_transaction_id is None
    )
    return _result(
        scenario_id="pulse_pack_purchase",
        purpose="Create the verified Pulse pack while recording no fictional payment.",
        turns=[turn],
        verification={
            "offer_id": str(offer.id),
            "before_pack_count": before_packs,
            "after_pack_count": after_packs,
            "before_payment_count": before_payments,
            "after_payment_count": after_payments,
            "purchase_transaction_id": (
                str(latest.purchase_transaction_id)
                if latest is not None and latest.purchase_transaction_id
                else None
            ),
            "verified_read": "pulse_pack_offers" in turn.verified_reads,
            "write_attempted": turn.write_attempted,
        },
        ok=ok,
        issue_title="Pulse-pack purchase violated verified-write/payment semantics",
        issue_detail=(
            "Expected exactly one new verified Pulse pack and no PaymentTransaction "
            "because the AI action records amount_paid=0."
        ),
        action=True,
    )


def case_purchase_and_book_standard(db: Session, workspace: Workspace) -> ScenarioResult:
    offer = _active_offer(db, workspace)
    patient = _patient_without_device_balance(
        db,
        workspace,
        device_key=offer.device_key,
    )
    _catalog, service, doctor, available, slot = _laser_booking_fixture(
        db,
        workspace,
        offer=offer,
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    before_appointments = _appointment_ids(db, workspace, patient)
    before_packs = _pulse_pack_count(db, workspace, patient)
    before_payments = _payment_count(db, workspace, patient)

    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_purchase_and_booking_standard",
        1,
        (
            f"اشتريلي باقة {offer.pulses_count} pulse على {offer.device_name} "
            f"واحجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')}. "
            "الجلسة نفسها عايزها عادية من غير استخدام باكيدج جلسات ولا pulse balance."
        ),
        None,
    )

    created = _created_appointments(
        db,
        workspace,
        patient,
        before_ids=before_appointments,
    )
    after_packs = _pulse_pack_count(db, workspace, patient)
    after_payments = _payment_count(db, workspace, patient)
    appointment = created[0] if len(created) == 1 else None
    ok = (
        "pulse_pack_offers" in turn.verified_reads
        and "availability" in turn.verified_reads
        and turn.write_attempted
        and after_packs == before_packs + 1
        and after_payments == before_payments
        and appointment is not None
        and str(appointment.service_id) == slot.service_id
        and str(appointment.doctor_id) == slot.doctor_id
        and appointment.laser_device_key == offer.device_key
        and appointment.billing_context == "standard"
    )
    return _result(
        scenario_id="pulse_purchase_and_booking_standard",
        purpose=(
            "Buy a Pulse pack and book a laser appointment in one turn while explicitly "
            "paying the appointment normally instead of consuming Pulse balance."
        ),
        turns=[turn],
        verification={
            "offer_id": str(offer.id),
            "appointment_count_created": len(created),
            "appointment_id": str(appointment.id) if appointment is not None else None,
            "billing_context": (
                appointment.billing_context if appointment is not None else None
            ),
            "laser_device_key": (
                appointment.laser_device_key if appointment is not None else None
            ),
            "pack_count_delta": after_packs - before_packs,
            "payment_count_delta": after_payments - before_payments,
            "verified_reads": turn.verified_reads,
        },
        ok=ok,
        issue_title="Compound Pulse purchase + standard booking was not executed correctly",
        issue_detail=(
            "Expected one verified Pulse-pack purchase, one exact laser booking with "
            "billing_context=standard, and no fictional payment transaction."
        ),
        action=True,
    )


def case_explicit_use_pulses_booking(
    db: Session,
    workspace: Workspace,
) -> ScenarioResult:
    patient = _patient_with_pulse_balance(db, workspace)
    balances = [
        row
        for row in list_patient_pulse_balances(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
        )
        if row.pulses_remaining > 0
    ]
    if not balances:
        raise RuntimeError("EVAL_INFRA_ERROR: no usable Pulse balance")
    balance = balances[0]
    offer = _active_offer_for_device(db, workspace, device_key=balance.device_key)
    _catalog, service, doctor, available, slot = _laser_booking_fixture(
        db,
        workspace,
        offer=offer,
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    before_appointments = _appointment_ids(db, workspace, patient)
    before_balance = _device_balance(
        db, workspace, patient, device_key=offer.device_key
    )

    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_explicit_use_booking",
        1,
        (
            f"احجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            f"على جهاز {offer.device_name} واستخدمي الـPulses اللي عندي."
        ),
        None,
    )

    created = _created_appointments(
        db, workspace, patient, before_ids=before_appointments
    )
    appointment = created[0] if len(created) == 1 else None
    after_balance = _device_balance(
        db, workspace, patient, device_key=offer.device_key
    )
    artifacts = _appointment_pulse_artifacts(db, workspace, appointment)
    reply = (turn.agent_response or "").lower()
    ok = (
        "availability" in turn.verified_reads
        and turn.write_attempted
        and appointment is not None
        and appointment.billing_context == "standard"
        and before_balance == after_balance
        and artifacts == {"usages": 0, "settlements": 0}
        and ("ريسبشن" in reply or "الاستقبال" in reply or "reception" in reply)
    )
    return _result(
        scenario_id="pulse_explicit_use_booking",
        purpose="Explicit customer Pulse billing preference must not mutate booking billing; Reception owns checkout.",
        turns=[turn],
        verification={
            "billing_context": appointment.billing_context if appointment is not None else None,
            "balance_before": before_balance,
            "balance_after": after_balance,
            "pulse_artifacts": artifacts,
            "verified_reads": turn.verified_reads,
        },
        ok=ok,
        issue_title="Agent applied or claimed a Pulse billing decision during booking",
        issue_detail="Expected standard booking, unchanged balance, no Pulse usage/settlement, and Reception guidance.",
        action=True,
    )

def case_purchase_then_book_with_pulses(
    db: Session,
    workspace: Workspace,
) -> ScenarioResult:
    offer = _active_offer(db, workspace)
    patient = _patient_without_device_balance(
        db,
        workspace,
        device_key=offer.device_key,
    )
    _catalog, service, doctor, available, slot = _laser_booking_fixture(
        db,
        workspace,
        offer=offer,
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    before_appointments = _appointment_ids(db, workspace, patient)
    before_packs = _pulse_pack_count(db, workspace, patient)
    before_payments = _payment_count(db, workspace, patient)

    first_response, first_turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_purchase_then_booking",
        1,
        f"اشتريلي باقة {offer.pulses_count} Pulse على {offer.device_name}",
        None,
    )
    _, second_turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_purchase_then_booking",
        2,
        (
            f"طب احجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            "على نفس الجهاز."
        ),
        first_response.conversation_id,
    )

    created = _created_appointments(
        db, workspace, patient, before_ids=before_appointments
    )
    appointment = created[0] if len(created) == 1 else None
    after_packs = _pulse_pack_count(db, workspace, patient)
    after_payments = _payment_count(db, workspace, patient)
    artifacts = _appointment_pulse_artifacts(db, workspace, appointment)
    ok = (
        "pulse_pack_offers" in first_turn.verified_reads
        and first_turn.write_attempted
        and "availability" in second_turn.verified_reads
        and second_turn.write_attempted
        and after_packs == before_packs + 1
        and after_payments == before_payments
        and appointment is not None
        and appointment.laser_device_key == offer.device_key
        and appointment.billing_context == "standard"
        and artifacts == {"usages": 0, "settlements": 0}
    )
    return _result(
        scenario_id="pulse_purchase_then_booking",
        purpose="A verified Pulse purchase may carry device continuity, never Pulse billing continuity.",
        turns=[first_turn, second_turn],
        verification={
            "expected_device_key": offer.device_key,
            "booked_device_key": appointment.laser_device_key if appointment is not None else None,
            "billing_context": appointment.billing_context if appointment is not None else None,
            "pack_count_delta": after_packs - before_packs,
            "payment_count_delta": after_payments - before_payments,
            "pulse_artifacts": artifacts,
        },
        ok=ok,
        issue_title="Verified purchase continuity leaked into appointment billing",
        issue_detail="Expected inherited device only, standard billing, and no Pulse settlement.",
        action=True,
    )

def case_existing_balance_normal_booking(
    db: Session,
    workspace: Workspace,
) -> ScenarioResult:
    patient = _patient_with_pulse_balance(db, workspace)
    balance = next(
        row
        for row in list_patient_pulse_balances(
            db,
            workspace_id=workspace.id,
            patient_id=patient.id,
        )
        if row.pulses_remaining > 0
    )
    offer = _active_offer_for_device(db, workspace, device_key=balance.device_key)
    _catalog, service, doctor, available, slot = _laser_booking_fixture(
        db, workspace, offer=offer
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    before_appointments = _appointment_ids(db, workspace, patient)
    before_balance = _device_balance(
        db, workspace, patient, device_key=offer.device_key
    )

    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_existing_balance_normal_booking",
        1,
        (
            f"احجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            f"على جهاز {offer.device_name}."
        ),
        None,
    )

    created = _created_appointments(
        db, workspace, patient, before_ids=before_appointments
    )
    appointment = created[0] if len(created) == 1 else None
    after_balance = _device_balance(
        db, workspace, patient, device_key=offer.device_key
    )
    artifacts = _appointment_pulse_artifacts(db, workspace, appointment)
    ok = (
        "availability" in turn.verified_reads
        and turn.write_attempted
        and appointment is not None
        and appointment.billing_context == "standard"
        and before_balance == after_balance
        and artifacts == {"usages": 0, "settlements": 0}
    )
    return _result(
        scenario_id="pulse_existing_balance_normal_booking",
        purpose="Existing Pulse entitlement must never auto-select Pulse billing on an Agent booking.",
        turns=[turn],
        verification={
            "billing_context": appointment.billing_context if appointment is not None else None,
            "balance_before": before_balance,
            "balance_after": after_balance,
            "pulse_artifacts": artifacts,
        },
        ok=ok,
        issue_title="Existing Pulse balance changed Agent booking billing",
        issue_detail="Expected standard booking with unchanged Pulse balance and no settlement.",
        action=True,
    )


def case_purchase_then_different_device_override(
    db: Session,
    workspace: Workspace,
) -> ScenarioResult:
    purchased_offer, booking_offer = _distinct_device_offers(db, workspace)
    patient = _active_patient(db, workspace)
    _catalog, service, doctor, available, slot = _laser_booking_fixture(
        db, workspace, offer=booking_offer
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    before_appointments = _appointment_ids(db, workspace, patient)

    first_response, first_turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_different_device_override",
        1,
        f"اشتريلي باقة {purchased_offer.pulses_count} Pulse على {purchased_offer.device_name}",
        None,
    )
    _, second_turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_different_device_override",
        2,
        (
            f"طب احجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')} "
            f"على {booking_offer.device_name}."
        ),
        first_response.conversation_id,
    )

    created = _created_appointments(
        db, workspace, patient, before_ids=before_appointments
    )
    appointment = created[0] if len(created) == 1 else None
    artifacts = _appointment_pulse_artifacts(db, workspace, appointment)
    ok = (
        first_turn.write_attempted
        and "availability" in second_turn.verified_reads
        and second_turn.write_attempted
        and appointment is not None
        and appointment.laser_device_key == booking_offer.device_key
        and appointment.laser_device_key != purchased_offer.device_key
        and appointment.billing_context == "standard"
        and artifacts == {"usages": 0, "settlements": 0}
    )
    return _result(
        scenario_id="pulse_different_device_override",
        purpose="An explicit booking device must override the device from a previous verified Pulse purchase.",
        turns=[first_turn, second_turn],
        verification={
            "purchased_device": purchased_offer.device_key,
            "explicit_booking_device": booking_offer.device_key,
            "booked_device": appointment.laser_device_key if appointment is not None else None,
            "billing_context": appointment.billing_context if appointment is not None else None,
        },
        ok=ok,
        issue_title="Previous Pulse purchase incorrectly overrode explicit booking device",
        issue_detail="Expected explicit booking device to win and billing to remain standard.",
        action=True,
    )


def case_billing_ledger_question(
    db: Session,
    workspace: Workspace,
) -> ScenarioResult:
    patient = _patient_with_pulse_balance(db, workspace)
    _, turn = send_turn(
        db,
        workspace,
        patient,
        "pulse_billing_ledger_question",
        1,
        "فاضل عليا كام فلوس في باقة الـPulse؟",
        None,
    )
    reads = set(turn.verified_reads)
    forbidden_reads = {"payments", "payment_ledger", "pulse_payments"}
    ok = (
        not turn.write_attempted
        and not reads.intersection(forbidden_reads)
        and (
            turn.handoff_state is not None
            or "ريسبشن" in (turn.agent_response or "")
            or "reception" in (turn.agent_response or "").lower()
        )
    )
    return _result(
        scenario_id="pulse_billing_ledger_question",
        purpose="Owned Pulse-pack payment-ledger questions stay receptionist-owned.",
        turns=[turn],
        verification={
            "verified_reads": turn.verified_reads,
            "write_attempted": turn.write_attempted,
            "handoff_state": turn.handoff_state,
        },
        ok=ok,
        issue_title="Agent expanded into Pulse payment-ledger ownership",
        issue_detail="Expected no invented financial ledger answer and Reception/handoff guidance.",
    )


def case_book_service_and_buy_pulses_for_other_unspecified_use(
    db: Session,
    workspace: Workspace,
) -> ScenarioResult:
    offer = _active_offer(db, workspace)
    patient = _active_patient(db, workspace)
    _catalog, service, doctor, available, slot = _standard_booking_fixture(
        db,
        workspace,
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    before_appointments = _appointment_ids(db, workspace, patient)
    before_packs = _pulse_pack_count(db, workspace, patient)
    before_payments = _payment_count(db, workspace, patient)

    _, turn = send_turn(
        db,
        workspace,
        patient,
        "book_service_buy_pulses_other_unspecified",
        1,
        (
            f"احجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')}، "
            f"وكمان اشتريلي باقة {offer.pulses_count} pulse على {offer.device_name} "
            "لحاجة تانية بعدين، مش للجلسة دي."
        ),
        None,
    )

    created = _created_appointments(
        db,
        workspace,
        patient,
        before_ids=before_appointments,
    )
    after_packs = _pulse_pack_count(db, workspace, patient)
    after_payments = _payment_count(db, workspace, patient)
    appointment = created[0] if len(created) == 1 else None
    ok = (
        "pulse_pack_offers" in turn.verified_reads
        and "availability" in turn.verified_reads
        and after_packs == before_packs + 1
        and after_payments == before_payments
        and appointment is not None
        and str(appointment.service_id) == slot.service_id
        and str(appointment.doctor_id) == slot.doctor_id
        and appointment.billing_context == "standard"
        and appointment.patient_package_id is None
        and appointment.laser_device_key is None
    )
    return _result(
        scenario_id="book_service_buy_pulses_other_unspecified",
        purpose=(
            "Book an unrelated non-laser service while buying a specific Pulse pack "
            "for an unspecified future use, without attaching Pulses to the appointment."
        ),
        turns=[turn],
        verification={
            "booked_service": service["name"],
            "pulse_offer_device": offer.device_name,
            "pulse_offer_count": offer.pulses_count,
            "appointment_count_created": len(created),
            "billing_context": (
                appointment.billing_context if appointment is not None else None
            ),
            "laser_device_key": (
                appointment.laser_device_key if appointment is not None else None
            ),
            "pack_count_delta": after_packs - before_packs,
            "payment_count_delta": after_payments - before_payments,
            "verified_reads": turn.verified_reads,
        },
        ok=ok,
        issue_title="Unrelated Pulse purchase leaked into the booked service",
        issue_detail=(
            "Expected independent standard booking plus Pulse-pack purchase. The "
            "unspecified future Pulse use must not change this appointment billing."
        ),
        action=True,
    )


def case_book_service_and_buy_pulses_for_retouch(
    db: Session,
    workspace: Workspace,
) -> ScenarioResult:
    offer = _active_offer(db, workspace)
    patient = _active_patient(db, workspace)
    _catalog, service, doctor, available, slot = _standard_booking_fixture(
        db,
        workspace,
    )
    local = slot.start_at.astimezone(ZoneInfo(available.timezone))
    before_appointments = _appointment_ids(db, workspace, patient)
    before_packs = _pulse_pack_count(db, workspace, patient)
    before_payments = _payment_count(db, workspace, patient)

    _, turn = send_turn(
        db,
        workspace,
        patient,
        "book_service_buy_pulses_retouch",
        1,
        (
            f"احجزيلي {service['name']} مع {doctor['name']} "
            f"يوم {local.date().isoformat()} الساعة {local.strftime('%H:%M')}، "
            f"واشتريلي كمان باقة {offer.pulses_count} pulse على {offer.device_name} "
            "عشان retouch بعدين. الـpulses مش للجلسة اللي بحجزها دلوقتي."
        ),
        None,
    )

    created = _created_appointments(
        db,
        workspace,
        patient,
        before_ids=before_appointments,
    )
    after_packs = _pulse_pack_count(db, workspace, patient)
    after_payments = _payment_count(db, workspace, patient)
    appointment = created[0] if len(created) == 1 else None
    ok = (
        "pulse_pack_offers" in turn.verified_reads
        and "availability" in turn.verified_reads
        and after_packs == before_packs + 1
        and after_payments == before_payments
        and appointment is not None
        and str(appointment.service_id) == slot.service_id
        and str(appointment.doctor_id) == slot.doctor_id
        and appointment.billing_context == "standard"
        and appointment.patient_package_id is None
        and appointment.laser_device_key is None
    )
    return _result(
        scenario_id="book_service_buy_pulses_retouch",
        purpose=(
            "Book an unrelated service while buying Pulses explicitly for a future "
            "retouch, ensuring the retouch purpose is not bound to the current booking."
        ),
        turns=[turn],
        verification={
            "booked_service": service["name"],
            "future_purpose": "retouch",
            "pulse_offer_device": offer.device_name,
            "pulse_offer_count": offer.pulses_count,
            "appointment_count_created": len(created),
            "billing_context": (
                appointment.billing_context if appointment is not None else None
            ),
            "laser_device_key": (
                appointment.laser_device_key if appointment is not None else None
            ),
            "pack_count_delta": after_packs - before_packs,
            "payment_count_delta": after_payments - before_payments,
            "verified_reads": turn.verified_reads,
        },
        ok=ok,
        issue_title="Retouch Pulse purpose leaked into the current booking",
        issue_detail=(
            "Expected independent standard booking plus verified Pulse-pack purchase. "
            "The future retouch purpose must not make the current appointment pulse_prepaid."
        ),
        action=True,
    )


CASES = [
    case_balance,
    case_owned_pack_remaining,
    case_offer_price,
    case_overage_price,
    case_counted_overage,
    case_purchase_without_payment,
    case_purchase_and_book_standard,
    case_existing_balance_normal_booking,
    case_explicit_use_pulses_booking,
    case_purchase_then_book_with_pulses,
    case_purchase_then_different_device_override,
    case_billing_ledger_question,
]

def run_case(engine, workspace_slug: str, case_fn) -> ScenarioResult:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        workspace = db.scalar(
            select(Workspace).where(Workspace.slug == workspace_slug)
        )
        if workspace is None:
            raise RuntimeError("Workspace not found")
        assert_demo_only(workspace)
        return case_fn(db, workspace)
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(
            id=case_fn.__name__.removeprefix("case_"),
            category="pulses",
            purpose="Execution failed before deterministic evaluation completed.",
            turns=[],
            state_before={},
            state_after={},
            db_verification={},
            evaluation=default_evaluation(db_ok=False, grounding_ok=False),
            issues=[
                {
                    "severity": "P1",
                    "title": "Pulse eval scenario execution error",
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


def main() -> None:
    args = parse_args()
    require_explicit_demo_eval()
    from app.core.config import settings

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    selected_case_names = set(args.case)
    cases = (
        [
            case
            for case in CASES
            if case.__name__.removeprefix("case_") in selected_case_names
        ]
        if selected_case_names
        else CASES
    )
    missing_case_names = selected_case_names - {
        case.__name__.removeprefix("case_") for case in cases
    }
    if missing_case_names:
        raise RuntimeError(
            "Unknown Pulse eval case(s): " + ", ".join(sorted(missing_case_names))
        )
    results = [run_case(engine, args.workspace_slug, case) for case in cases]
    summary = {
        "scenarios_run": len(results),
        "fully_correct": sum(not row.issues and row.execution_error is None for row in results),
        "failed": sum(bool(row.issues) or row.execution_error is not None for row in results),
        "tokens": batch_token_summary(results),
        "latency_ms": {
            row.id: [turn.latency_ms for turn in row.turns]
            for row in results
        },
    }
    payload = {
        "run_metadata": {
            "git_sha": args.git_sha,
            "workspace": args.workspace_slug,
            "generated_at": datetime.now(UTC).isoformat(),
            "suite": "pulse_domain",
        },
        "scenario_results": [jsonable(asdict(row)) for row in results],
        "batch_summary": summary,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pulse_domain_eval.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    printable = {
        "batch_summary": summary,
        "scenario_results": [jsonable(asdict(row)) for row in results],
    }
    if args.compact:
        printable = {
            "batch_summary": summary,
            "scenario_results": [
                {
                    "id": row.id,
                    "issues": row.issues,
                    "execution_error": row.execution_error,
                    "db_verification": row.db_verification,
                    "turns": [
                        {
                            "user_message": turn.user_message,
                            "agent_response": turn.agent_response,
                            "latency_ms": turn.latency_ms,
                            "verified_reads": turn.verified_reads,
                            "write_attempted": turn.write_attempted,
                            "write_result": turn.write_result,
                            "token_usage": turn.token_usage,
                        }
                        for turn in row.turns
                    ],
                }
                for row in results
            ],
        }
    rendered = json.dumps(
        printable,
        ensure_ascii=False,
        separators=(",", ":") if args.compact else None,
        indent=None if args.compact else 2,
    )
    print(
        ("PULSE_DOMAIN_COMPACT=" + rendered) if args.compact else rendered,
        flush=True,
    )


if __name__ == "__main__":
    main()
