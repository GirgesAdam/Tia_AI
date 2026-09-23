from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.clinic.authority import (
    ClinicIntegrationAuthorityError,
    require_tia_workspace_domain_write,
)
from app.models.appointment import Appointment
from app.services.payments import (
    PaymentOperationError,
    get_appointment_payment_summary,
    record_payment,
    set_appointment_discount,
)
from app.services.pulse_billing import (
    PulseBillingError,
    checkout_appointment_pulses,
    get_appointment_pulse_settlement,
)


class AppointmentCheckoutError(ValueError):
    pass


def checkout_appointment(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
    amount_minor: int,
    payment_method: str,
    discount_minor: int,
    external_reference: str | None,
    pulse_mode: str,
    pulse_pack_offer_id: UUID | None,
    created_by_user_id: UUID | None,
    idempotency_key: str | None,
) -> None:
    if amount_minor < 0:
        raise AppointmentCheckoutError("Checkout amount cannot be negative.")
    try:
        require_tia_workspace_domain_write(
            db,
            workspace_id=workspace_id,
            domain="payments",
        )
    except ClinicIntegrationAuthorityError as exc:
        raise AppointmentCheckoutError(str(exc)) from exc

    appointment = db.scalar(
        select(Appointment)
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.id == appointment_id,
        )
        .with_for_update()
    )
    if appointment is None:
        raise AppointmentCheckoutError("Appointment not found.")

    if pulse_mode != "none":
        try:
            checkout_appointment_pulses(
                db,
                workspace_id=workspace_id,
                appointment_id=appointment_id,
                mode=pulse_mode,
                offer_id=pulse_pack_offer_id,
                changed_by_user_id=created_by_user_id,
                idempotency_key=idempotency_key,
            )
        except PulseBillingError as exc:
            raise AppointmentCheckoutError(str(exc)) from exc
    elif appointment.billing_context == "pulse_prepaid":
        settlement = get_appointment_pulse_settlement(
            db,
            workspace_id=workspace_id,
            appointment_id=appointment_id,
        )
        if settlement is None or settlement.resolution == "pending":
            raise AppointmentCheckoutError(
                "Resolve the pulse usage before recording this appointment payment."
            )

    try:
        if amount_minor > 0:
            record_payment(
                db,
                workspace_id=workspace_id,
                appointment_id=appointment_id,
                amount_minor=amount_minor,
                payment_method=payment_method,
                discount_minor=discount_minor,
                external_reference=external_reference,
                created_by_user_id=created_by_user_id,
                idempotency_key=idempotency_key,
            )
            return

        set_appointment_discount(
            db,
            workspace_id=workspace_id,
            appointment_id=appointment_id,
            discount_minor=discount_minor,
            created_by_user_id=created_by_user_id,
        )
        summary = get_appointment_payment_summary(
            db,
            workspace_id=workspace_id,
            appointment_id=appointment_id,
        )
        if summary.balance_minor > 0:
            raise AppointmentCheckoutError(
                "This checkout still has an outstanding balance. Enter a payment amount."
            )
    except PaymentOperationError as exc:
        raise AppointmentCheckoutError(str(exc)) from exc
