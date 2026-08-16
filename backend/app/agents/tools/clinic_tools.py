from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain_core.tools import BaseTool, tool
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_action import AgentAction
from app.models.appointment import Appointment
from app.models.appointment_status_history import AppointmentStatusHistory
from app.models.branch import Branch
from app.models.conversation import Conversation
from app.models.doctor import Doctor
from app.models.doctor_branch import DoctorBranch
from app.models.doctor_service import DoctorService
from app.models.lead import Lead
from app.models.patient import Patient
from app.models.service import Service
from app.models.staff import Staff
from app.models.workspace import Workspace
from app.services.outbound_communications import (
    OutboundCommunicationError,
    queue_patient_email,
)
from app.services.booking import (
    BookingRuleError,
    calculate_availability,
    find_exact_slot,
    get_effective_booking_settings,
)


@dataclass(frozen=True)
class AgentToolContext:
    db: Session
    workspace: Workspace
    patient: Patient
    conversation: Conversation
    run_id: UUID


def _json(payload: dict | list) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID from a tool result.") from exc


def _money(price_minor: int, currency: str) -> str:
    value = Decimal(price_minor) / Decimal(100)
    if value == value.to_integral():
        amount = f"{int(value):,}"
    else:
        amount = f"{value:,.2f}"
    if currency.upper() == "EGP":
        return f"{amount} EGP"
    return f"{amount} {currency.upper()}"


def _availability_display_context(
    ctx: AgentToolContext,
    *,
    branch_id: UUID,
    service_id: UUID,
    doctor_ids: set[UUID],
) -> tuple[str | None, str | None, dict[UUID, str]]:
    branch = ctx.db.scalar(
        select(Branch).where(
            Branch.workspace_id == ctx.workspace.id,
            Branch.id == branch_id,
        )
    )
    service = ctx.db.scalar(
        select(Service).where(
            Service.workspace_id == ctx.workspace.id,
            Service.id == service_id,
        )
    )

    doctor_names: dict[UUID, str] = {}
    if doctor_ids:
        rows = ctx.db.execute(
            select(Doctor.id, Staff.first_name, Staff.last_name)
            .join(
                Staff,
                (Staff.workspace_id == Doctor.workspace_id)
                & (Staff.id == Doctor.staff_id),
            )
            .where(
                Doctor.workspace_id == ctx.workspace.id,
                Doctor.id.in_(doctor_ids),
            )
        ).all()
        for doctor_id, first_name, last_name in rows:
            full_name = f"{first_name or ''} {last_name or ''}".strip()
            doctor_names[doctor_id] = full_name or "الدكتور المتاح"

    return (
        branch.name if branch else None,
        service.name if service else None,
        doctor_names,
    )


def _filter_slots_by_local_window(
    slots: list,
    *,
    tz: ZoneInfo,
    lower_bound: time | None,
    upper_bound: time | None,
) -> list[tuple[object, datetime]]:
    filtered: list[tuple[object, datetime]] = []

    for slot in slots:
        local_start = slot.start_at.astimezone(tz)
        local_end = slot.end_at.astimezone(tz)

        start_time = local_start.timetz().replace(tzinfo=None)
        end_time = local_end.timetz().replace(tzinfo=None)

        if lower_bound and start_time < lower_bound:
            continue

        # If the customer says "من 8 لحد 9", the whole appointment must
        # fit inside that window, not merely start before 9.
        if upper_bound and end_time > upper_bound:
            continue

        filtered.append((slot, local_start))

    return filtered


def _service_matches(
    ctx: AgentToolContext,
    search: str,
) -> list[Service]:
    stmt = select(Service).where(
        Service.workspace_id == ctx.workspace.id,
        Service.is_active.is_(True),
    )
    search = search.strip()
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Service.name.ilike(pattern),
                Service.category.ilike(pattern),
                Service.description.ilike(pattern),
            )
        )
    return list(ctx.db.scalars(stmt.order_by(Service.name).limit(20)))


def _active_branches(ctx: AgentToolContext) -> list[Branch]:
    return list(
        ctx.db.scalars(
            select(Branch)
            .where(
                Branch.workspace_id == ctx.workspace.id,
                Branch.is_active.is_(True),
            )
            .order_by(Branch.name)
        )
    )


def _availability_payload(
    ctx: AgentToolContext,
    *,
    branch: Branch,
    service: Service,
    booking_date: date,
    doctor_id: UUID | None,
    lower_bound: time | None,
    upper_bound: time | None,
    exclude_appointment_id: UUID | None = None,
) -> dict:
    timezone_name, slots = calculate_availability(
        db=ctx.db,
        workspace=ctx.workspace,
        branch_id=branch.id,
        service_id=service.id,
        booking_date=booking_date,
        doctor_id=doctor_id,
        exclude_appointment_id=exclude_appointment_id,
    )
    tz = ZoneInfo(timezone_name)
    filtered_slots = _filter_slots_by_local_window(
        slots,
        tz=tz,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )

    branch_name, service_name, doctor_names = _availability_display_context(
        ctx,
        branch_id=branch.id,
        service_id=service.id,
        doctor_ids={slot.doctor_id for slot, _ in filtered_slots},
    )

    result_slots = []
    for slot, local_start in filtered_slots[:12]:
        local_end = slot.end_at.astimezone(tz)
        result_slots.append(
            {
                "branch_id": str(slot.branch_id),
                "branch_name": branch_name,
                "doctor_id": str(slot.doctor_id),
                "doctor_name": doctor_names.get(
                    slot.doctor_id,
                    "الدكتور المتاح",
                ),
                "service_id": str(slot.service_id),
                "service_name": service_name,
                "start_local": local_start.isoformat(),
                "end_local": local_end.isoformat(),
                "start_time_24h": local_start.strftime("%H:%M"),
                "end_time_24h": local_end.strftime("%H:%M"),
                "timezone": timezone_name,
                "price": _money(slot.price_minor, slot.currency),
            }
        )

    return {
        "date": booking_date.isoformat(),
        "timezone": timezone_name,
        "branch": {
            "branch_id": str(branch.id),
            "branch_name": branch.name,
        },
        "service": {
            "service_id": str(service.id),
            "service_name": service.name,
            "duration_minutes": service.duration_minutes,
            "price": _money(service.price_minor, service.currency),
        },
        "slots": result_slots,
        "matching_slot_count": len(filtered_slots),
        "more_slots_available": len(filtered_slots) > len(result_slots),
    }


def _record_action(
    ctx: AgentToolContext,
    *,
    tool_name: str,
    action_type: str,
    status: str,
    input_payload: dict,
    output_payload: dict,
    appointment_id: UUID | None = None,
    error_message: str | None = None,
) -> None:
    ctx.db.add(
        AgentAction(
            workspace_id=ctx.workspace.id,
            conversation_id=ctx.conversation.id,
            patient_id=ctx.patient.id,
            appointment_id=appointment_id,
            run_id=ctx.run_id,
            tool_name=tool_name,
            action_type=action_type,
            status=status,
            input_json=input_payload,
            output_json=output_payload,
            error_message=error_message,
        )
    )
    ctx.db.commit()


def _history(
    ctx: AgentToolContext,
    appointment: Appointment,
    *,
    from_status: str | None,
    to_status: str,
    reason: str,
    metadata: dict | None = None,
) -> None:
    ctx.db.add(
        AppointmentStatusHistory(
            workspace_id=ctx.workspace.id,
            appointment_id=appointment.id,
            changed_by_user_id=None,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            metadata_json=metadata or {},
        )
    )


def _appointment_summary(ctx: AgentToolContext, appointment: Appointment) -> dict:
    service = ctx.db.scalar(
        select(Service).where(
            Service.workspace_id == ctx.workspace.id,
            Service.id == appointment.service_id,
        )
    )
    branch = ctx.db.scalar(
        select(Branch).where(
            Branch.workspace_id == ctx.workspace.id,
            Branch.id == appointment.branch_id,
        )
    )
    doctor_row = ctx.db.execute(
        select(Doctor, Staff)
        .join(
            Staff,
            (Staff.workspace_id == Doctor.workspace_id) & (Staff.id == Doctor.staff_id),
        )
        .where(
            Doctor.workspace_id == ctx.workspace.id,
            Doctor.id == appointment.doctor_id,
        )
    ).first()
    doctor_name = None
    if doctor_row is not None:
        _, staff = doctor_row
        doctor_name = f"{staff.first_name} {staff.last_name}".strip()

    timezone_name = ctx.workspace.timezone
    if branch is not None:
        timezone_name = branch.timezone or ctx.workspace.timezone
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc

    return {
        "appointment_id": str(appointment.id),
        "status": appointment.status,
        "service": service.name if service else None,
        "branch": branch.name if branch else None,
        "doctor": doctor_name,
        "start_local": appointment.start_at.astimezone(tz).isoformat(),
        "end_local": appointment.end_at.astimezone(tz).isoformat(),
        "timezone": getattr(tz, "key", "UTC"),
        "price": _money(appointment.price_minor, appointment.currency),
    }


def _set_handoff(ctx: AgentToolContext) -> None:
    ctx.conversation.status = "pending"
    ctx.db.commit()


def build_clinic_tools(ctx: AgentToolContext) -> list[BaseTool]:
    @tool
    def get_customer_profile() -> str:
        """Get the current customer's own CRM profile. Never use this to access another patient."""
        payload = {
            "ok": True,
            "patient": {
                "patient_id": str(ctx.patient.id),
                "first_name": ctx.patient.first_name,
                "last_name": ctx.patient.last_name,
                "phone": ctx.patient.phone,
                "email": ctx.patient.email,
                "preferred_branch_id": (
                    str(ctx.patient.preferred_branch_id) if ctx.patient.preferred_branch_id else None
                ),
                "preferred_language": ctx.patient.preferred_language,
            },
        }
        _record_action(
            ctx,
            tool_name="get_customer_profile",
            action_type="crm_read",
            status="success",
            input_payload={},
            output_payload=payload,
        )
        return _json(payload)

    @tool
    def search_services(search: str = "") -> str:
        """Search active clinic services and return real names, prices, durations, and medical-review flags."""
        search = search.strip()
        stmt = select(Service).where(
            Service.workspace_id == ctx.workspace.id,
            Service.is_active.is_(True),
        )
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Service.name.ilike(pattern),
                    Service.category.ilike(pattern),
                    Service.description.ilike(pattern),
                )
            )
        rows = list(ctx.db.scalars(stmt.order_by(Service.name).limit(20)))
        services = [
            {
                "service_id": str(row.id),
                "name": row.name,
                "category": row.category,
                "description": row.description,
                "duration_minutes": row.duration_minutes,
                "price": _money(row.price_minor, row.currency),
                "price_minor": row.price_minor,
                "currency": row.currency,
                "requires_medical_review": row.requires_medical_review,
            }
            for row in rows
        ]
        payload = {"ok": True, "services": services}
        _record_action(
            ctx,
            tool_name="search_services",
            action_type="clinic_read",
            status="success",
            input_payload={"search": search},
            output_payload=payload,
        )
        return _json(payload)

    @tool
    def list_branches() -> str:
        """List active clinic branches with their real location and contact details."""
        rows = list(
            ctx.db.scalars(
                select(Branch)
                .where(
                    Branch.workspace_id == ctx.workspace.id,
                    Branch.is_active.is_(True),
                )
                .order_by(Branch.name)
            )
        )
        branches = [
            {
                "branch_id": str(row.id),
                "name": row.name,
                "phone": row.phone,
                "address": ", ".join(
                    part
                    for part in [row.address_line1, row.address_line2, row.city, row.state]
                    if part
                )
                or None,
                "timezone": row.timezone or ctx.workspace.timezone,
            }
            for row in rows
        ]
        payload = {"ok": True, "branches": branches}
        _record_action(
            ctx,
            tool_name="list_branches",
            action_type="clinic_read",
            status="success",
            input_payload={},
            output_payload=payload,
        )
        return _json(payload)

    @tool
    def list_doctors(branch_id: str = "", service_id: str = "") -> str:
        """List active bookable doctors, optionally filtered by a branch ID and/or service ID returned by other tools."""
        try:
            branch_uuid = _uuid(branch_id, "branch_id") if branch_id else None
            service_uuid = _uuid(service_id, "service_id") if service_id else None

            stmt = (
                select(Doctor, Staff)
                .join(
                    Staff,
                    (Staff.workspace_id == Doctor.workspace_id) & (Staff.id == Doctor.staff_id),
                )
                .where(
                    Doctor.workspace_id == ctx.workspace.id,
                    Doctor.is_active.is_(True),
                    Doctor.booking_enabled.is_(True),
                    Staff.is_active.is_(True),
                )
            )
            if branch_uuid is not None:
                stmt = stmt.join(
                    DoctorBranch,
                    (DoctorBranch.workspace_id == Doctor.workspace_id)
                    & (DoctorBranch.doctor_id == Doctor.id),
                ).where(
                    DoctorBranch.branch_id == branch_uuid,
                    DoctorBranch.is_active.is_(True),
                )
            if service_uuid is not None:
                stmt = stmt.join(
                    DoctorService,
                    (DoctorService.workspace_id == Doctor.workspace_id)
                    & (DoctorService.doctor_id == Doctor.id),
                ).where(
                    DoctorService.service_id == service_uuid,
                    DoctorService.is_active.is_(True),
                )

            rows = list(ctx.db.execute(stmt.order_by(Staff.first_name, Staff.last_name)).all())
            doctors = []
            seen: set[UUID] = set()
            for doctor, staff in rows:
                if doctor.id in seen:
                    continue
                seen.add(doctor.id)
                doctors.append(
                    {
                        "doctor_id": str(doctor.id),
                        "name": f"{staff.first_name} {staff.last_name}".strip(),
                        "specialization": doctor.specialization,
                    }
                )
            payload = {"ok": True, "doctors": doctors}
            _record_action(
                ctx,
                tool_name="list_doctors",
                action_type="clinic_read",
                status="success",
                input_payload={"branch_id": branch_id, "service_id": service_id},
                output_payload=payload,
            )
            return _json(payload)
        except ValueError as exc:
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="list_doctors",
                action_type="clinic_read",
                status="error",
                input_payload={"branch_id": branch_id, "service_id": service_id},
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def get_booking_options(
        service_search: str,
        booking_date: str,
        not_before_time: str = "",
        not_after_time: str = "",
        branch_id: str = "",
        doctor_id: str = "",
    ) -> str:
        """High-level booking discovery tool.

        Prefer this tool for requests like:
        - "عايزة أحجز ليزر بكرة بعد 6"
        - "فيه مواعيد ليزر بكرة من 8 لحد 9؟"

        It resolves the service, branch, and real availability in one tool call
        whenever the workspace data is unambiguous.

        If more than one service or branch matches, it returns a small set of
        choices instead of guessing.
        """
        inputs = {
            "service_search": service_search,
            "booking_date": booking_date,
            "not_before_time": not_before_time,
            "not_after_time": not_after_time,
            "branch_id": branch_id,
            "doctor_id": doctor_id,
        }

        try:
            requested_date = date.fromisoformat(booking_date)
            lower_bound = time.fromisoformat(not_before_time) if not_before_time else None
            upper_bound = time.fromisoformat(not_after_time) if not_after_time else None

            if lower_bound and upper_bound and lower_bound > upper_bound:
                raise ValueError("not_before_time cannot be later than not_after_time.")

            services = _service_matches(ctx, service_search)
            if not services:
                payload = {
                    "ok": False,
                    "reason": "service_not_found",
                    "message": "No active service matched the customer's request.",
                    "service_search": service_search,
                }
                _record_action(
                    ctx,
                    tool_name="get_booking_options",
                    action_type="booking_discovery",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                )
                return _json(payload)

            if len(services) > 1:
                payload = {
                    "ok": True,
                    "needs_service_choice": True,
                    "services": [
                        {
                            "service_id": str(service.id),
                            "service_name": service.name,
                            "category": service.category,
                            "duration_minutes": service.duration_minutes,
                            "price": _money(service.price_minor, service.currency),
                        }
                        for service in services[:8]
                    ],
                }
                _record_action(
                    ctx,
                    tool_name="get_booking_options",
                    action_type="booking_discovery",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                )
                return _json(payload)

            service = services[0]

            branches = _active_branches(ctx)
            if branch_id:
                branch_uuid = _uuid(branch_id, "branch_id")
                branches = [branch for branch in branches if branch.id == branch_uuid]
                if not branches:
                    raise BookingRuleError("Branch not found or inactive.")
            elif ctx.patient.preferred_branch_id:
                preferred = [
                    branch
                    for branch in branches
                    if branch.id == ctx.patient.preferred_branch_id
                ]
                if preferred:
                    branches = preferred

            if not branches:
                payload = {
                    "ok": False,
                    "reason": "no_active_branch",
                    "message": "No active clinic branch is available.",
                }
                _record_action(
                    ctx,
                    tool_name="get_booking_options",
                    action_type="booking_discovery",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                )
                return _json(payload)

            if len(branches) > 1:
                payload = {
                    "ok": True,
                    "needs_branch_choice": True,
                    "service": {
                        "service_id": str(service.id),
                        "service_name": service.name,
                    },
                    "branches": [
                        {
                            "branch_id": str(branch.id),
                            "branch_name": branch.name,
                            "city": branch.city,
                            "address": branch.address,
                        }
                        for branch in branches[:8]
                    ],
                }
                _record_action(
                    ctx,
                    tool_name="get_booking_options",
                    action_type="booking_discovery",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                )
                return _json(payload)

            branch = branches[0]
            doctor_uuid = _uuid(doctor_id, "doctor_id") if doctor_id else None

            availability = _availability_payload(
                ctx,
                branch=branch,
                service=service,
                booking_date=requested_date,
                doctor_id=doctor_uuid,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )

            payload = {
                "ok": True,
                "needs_service_choice": False,
                "needs_branch_choice": False,
                "requested_time_window": {
                    "not_before_time": not_before_time or None,
                    "not_after_time": not_after_time or None,
                },
                **availability,
            }
            _record_action(
                ctx,
                tool_name="get_booking_options",
                action_type="booking_discovery",
                status="success",
                input_payload=inputs,
                output_payload=payload,
            )
            return _json(payload)

        except (ValueError, BookingRuleError) as exc:
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="get_booking_options",
                action_type="booking_discovery",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def get_reschedule_options(
        booking_date: str,
        service_search: str = "",
        not_before_time: str = "",
        not_after_time: str = "",
    ) -> str:
        """High-level rescheduling discovery tool.

        Prefer this tool when the customer wants to move an existing appointment.
        It finds the customer's upcoming appointment and available replacement
        slots in one tool call.

        If multiple appointments match, it returns choices instead of guessing.
        """
        inputs = {
            "booking_date": booking_date,
            "service_search": service_search,
            "not_before_time": not_before_time,
            "not_after_time": not_after_time,
        }

        try:
            requested_date = date.fromisoformat(booking_date)
            lower_bound = time.fromisoformat(not_before_time) if not_before_time else None
            upper_bound = time.fromisoformat(not_after_time) if not_after_time else None

            if lower_bound and upper_bound and lower_bound > upper_bound:
                raise ValueError("not_before_time cannot be later than not_after_time.")

            stmt = (
                select(Appointment)
                .join(
                    Service,
                    (Service.workspace_id == Appointment.workspace_id)
                    & (Service.id == Appointment.service_id),
                )
                .where(
                    Appointment.workspace_id == ctx.workspace.id,
                    Appointment.patient_id == ctx.patient.id,
                    Appointment.status.in_(("pending", "confirmed")),
                    Appointment.start_at >= datetime.now(timezone.utc) - timedelta(hours=6),
                )
                .order_by(Appointment.start_at)
            )

            if service_search.strip():
                pattern = f"%{service_search.strip()}%"
                stmt = stmt.where(
                    or_(
                        Service.name.ilike(pattern),
                        Service.category.ilike(pattern),
                        Service.description.ilike(pattern),
                    )
                )

            appointments = list(ctx.db.scalars(stmt.limit(10)))

            if not appointments:
                payload = {
                    "ok": False,
                    "reason": "appointment_not_found",
                    "message": "No matching upcoming appointment was found.",
                }
                _record_action(
                    ctx,
                    tool_name="get_reschedule_options",
                    action_type="appointment_reschedule_discovery",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                )
                return _json(payload)

            if len(appointments) > 1:
                payload = {
                    "ok": True,
                    "needs_appointment_choice": True,
                    "appointments": [
                        _appointment_summary(ctx, appointment)
                        for appointment in appointments[:8]
                    ],
                }
                _record_action(
                    ctx,
                    tool_name="get_reschedule_options",
                    action_type="appointment_reschedule_discovery",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                )
                return _json(payload)

            current = appointments[0]
            branch = ctx.db.scalar(
                select(Branch).where(
                    Branch.workspace_id == ctx.workspace.id,
                    Branch.id == current.branch_id,
                    Branch.is_active.is_(True),
                )
            )
            service = ctx.db.scalar(
                select(Service).where(
                    Service.workspace_id == ctx.workspace.id,
                    Service.id == current.service_id,
                    Service.is_active.is_(True),
                )
            )
            if branch is None or service is None:
                raise BookingRuleError(
                    "The current appointment's branch or service is no longer active."
                )

            availability = _availability_payload(
                ctx,
                branch=branch,
                service=service,
                booking_date=requested_date,
                doctor_id=current.doctor_id,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                exclude_appointment_id=current.id,
            )

            payload = {
                "ok": True,
                "needs_appointment_choice": False,
                "current_appointment": _appointment_summary(ctx, current),
                "requested_time_window": {
                    "not_before_time": not_before_time or None,
                    "not_after_time": not_after_time or None,
                },
                **availability,
            }
            _record_action(
                ctx,
                tool_name="get_reschedule_options",
                action_type="appointment_reschedule_discovery",
                status="success",
                input_payload=inputs,
                output_payload=payload,
                appointment_id=current.id,
            )
            return _json(payload)

        except (ValueError, BookingRuleError) as exc:
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="get_reschedule_options",
                action_type="appointment_reschedule_discovery",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def get_available_slots(
        branch_id: str,
        service_id: str,
        booking_date: str,
        doctor_id: str = "",
        not_before_time: str = "",
        not_after_time: str = "",
    ) -> str:
        """Get real available appointment slots.

        booking_date must be YYYY-MM-DD.
        IDs must come from clinic tools.

        IMPORTANT time rule:
        - If the customer says "بعد 6 مساءً" / "from 6 PM", pass not_before_time="18:00".
        - If the customer gives an upper time limit, pass not_after_time in local 24-hour HH:MM.
        - Do not fetch unfiltered slots and then guess whether a requested time window is available.
        """
        inputs = {
            "branch_id": branch_id,
            "service_id": service_id,
            "booking_date": booking_date,
            "doctor_id": doctor_id,
            "not_before_time": not_before_time,
            "not_after_time": not_after_time,
        }
        try:
            branch_uuid = _uuid(branch_id, "branch_id")
            service_uuid = _uuid(service_id, "service_id")
            doctor_uuid = _uuid(doctor_id, "doctor_id") if doctor_id else None
            requested_date = date.fromisoformat(booking_date)

            lower_bound = time.fromisoformat(not_before_time) if not_before_time else None
            upper_bound = time.fromisoformat(not_after_time) if not_after_time else None

            if lower_bound and upper_bound and lower_bound > upper_bound:
                raise ValueError("not_before_time cannot be later than not_after_time.")

            timezone_name, slots = calculate_availability(
                db=ctx.db,
                workspace=ctx.workspace,
                branch_id=branch_uuid,
                service_id=service_uuid,
                booking_date=requested_date,
                doctor_id=doctor_uuid,
            )
            tz = ZoneInfo(timezone_name)

            filtered_slots = _filter_slots_by_local_window(
                slots,
                tz=tz,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )

            branch_name, service_name, doctor_names = _availability_display_context(
                ctx,
                branch_id=branch_uuid,
                service_id=service_uuid,
                doctor_ids={slot.doctor_id for slot, _ in filtered_slots},
            )

            result_slots = []
            for slot, local_start in filtered_slots[:12]:
                local_end = slot.end_at.astimezone(tz)
                result_slots.append(
                    {
                        "branch_id": str(slot.branch_id),
                        "branch_name": branch_name,
                        "doctor_id": str(slot.doctor_id),
                        "doctor_name": doctor_names.get(
                            slot.doctor_id,
                            "الدكتور المتاح",
                        ),
                        "service_id": str(slot.service_id),
                        "service_name": service_name,
                        "start_local": local_start.isoformat(),
                        "end_local": local_end.isoformat(),
                        "start_time_24h": local_start.strftime("%H:%M"),
                        "end_time_24h": local_end.strftime("%H:%M"),
                        "timezone": timezone_name,
                        "price": _money(slot.price_minor, slot.currency),
                    }
                )

            payload = {
                "ok": True,
                "date": booking_date,
                "timezone": timezone_name,
                "requested_time_window": {
                    "not_before_time": not_before_time or None,
                    "not_after_time": not_after_time or None,
                },
                "slots": result_slots,
                "matching_slot_count": len(filtered_slots),
                "more_slots_available": len(filtered_slots) > len(result_slots),
            }
            _record_action(
                ctx,
                tool_name="get_available_slots",
                action_type="availability_read",
                status="success",
                input_payload=inputs,
                output_payload=payload,
            )
            return _json(payload)
        except (ValueError, BookingRuleError) as exc:
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="get_available_slots",
                action_type="availability_read",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def get_customer_appointments(include_past: bool = False) -> str:
        """Get the current customer's real appointments. Use before answering questions about their bookings."""
        stmt = select(Appointment).where(
            Appointment.workspace_id == ctx.workspace.id,
            Appointment.patient_id == ctx.patient.id,
        )
        if not include_past:
            stmt = stmt.where(
                Appointment.status.in_(("pending", "confirmed", "checked_in", "in_progress")),
                Appointment.start_at >= datetime.now(timezone.utc) - timedelta(hours=6),
            )
        rows = list(ctx.db.scalars(stmt.order_by(Appointment.start_at).limit(30)))
        appointments = [_appointment_summary(ctx, row) for row in rows]
        payload = {"ok": True, "appointments": appointments}
        _record_action(
            ctx,
            tool_name="get_customer_appointments",
            action_type="booking_read",
            status="success",
            input_payload={"include_past": include_past},
            output_payload=payload,
        )
        return _json(payload)

    @tool
    def book_appointment(
        branch_id: str,
        service_id: str,
        doctor_id: str,
        start_at: str,
        customer_note: str = "",
    ) -> str:
        """Create a real appointment after the customer has clearly chosen an exact offered slot.

Use the INTERNAL OPERATIONAL CONTEXT from the previous availability call when the customer says
things like "احجزلي الساعة 7 من المواعيد اللي عرضتها". Reuse the hidden branch_id/service_id/
doctor_id/start_local values from that offered slot; never ask the customer for internal IDs.
The slot is revalidated against PostgreSQL before the appointment is created."""
        inputs = {
            "branch_id": branch_id,
            "service_id": service_id,
            "doctor_id": doctor_id,
            "start_at": start_at,
            "customer_note": customer_note,
        }
        try:
            if ctx.patient.status == "blocked":
                raise BookingRuleError("This customer is blocked from new appointments.")
            branch_uuid = _uuid(branch_id, "branch_id")
            service_uuid = _uuid(service_id, "service_id")
            doctor_uuid = _uuid(doctor_id, "doctor_id")
            requested_start = datetime.fromisoformat(start_at)
            if requested_start.tzinfo is None or requested_start.utcoffset() is None:
                raise ValueError("start_at must include the timezone offset from availability results.")

            slot = find_exact_slot(
                db=ctx.db,
                workspace=ctx.workspace,
                branch_id=branch_uuid,
                service_id=service_uuid,
                doctor_id=doctor_uuid,
                requested_start_at=requested_start,
            )
            settings = get_effective_booking_settings(ctx.db, ctx.workspace.id)
            initial_status = "pending" if settings.require_confirmation else "confirmed"

            lead = ctx.db.scalar(
                select(Lead)
                .where(
                    Lead.workspace_id == ctx.workspace.id,
                    Lead.patient_id == ctx.patient.id,
                    Lead.status.notin_(("lost", "spam", "won")),
                    or_(Lead.service_id == service_uuid, Lead.service_id.is_(None)),
                )
                .order_by(Lead.created_at.desc())
                .limit(1)
            )

            appointment = Appointment(
                workspace_id=ctx.workspace.id,
                patient_id=ctx.patient.id,
                branch_id=branch_uuid,
                doctor_id=doctor_uuid,
                service_id=service_uuid,
                lead_id=lead.id if lead else None,
                created_by_user_id=None,
                status=initial_status,
                source="ai",
                start_at=slot.start_at,
                end_at=slot.end_at,
                busy_start_at=slot.busy_start_at,
                busy_end_at=slot.busy_end_at,
                duration_minutes=slot.duration_minutes,
                price_minor=slot.price_minor,
                currency=slot.currency,
                customer_note=customer_note.strip() or None,
                idempotency_key=(
                    f"agent:{ctx.run_id}:book:{ctx.patient.id}:{doctor_uuid}:{slot.start_at.isoformat()}"
                )[:128],
                confirmed_at=datetime.now(timezone.utc) if initial_status == "confirmed" else None,
            )
            ctx.db.add(appointment)
            ctx.db.flush()
            _history(
                ctx,
                appointment,
                from_status=None,
                to_status=initial_status,
                reason="appointment_created_by_ai",
            )
            if lead is not None:
                if lead.service_id is None:
                    lead.service_id = service_uuid
                lead.status = "booked"
            ctx.db.add(
                AgentAction(
                    workspace_id=ctx.workspace.id,
                    conversation_id=ctx.conversation.id,
                    patient_id=ctx.patient.id,
                    appointment_id=appointment.id,
                    run_id=ctx.run_id,
                    tool_name="book_appointment",
                    action_type="appointment_create",
                    status="success",
                    input_json=inputs,
                    output_json={"appointment_id": str(appointment.id), "status": initial_status},
                )
            )
            ctx.db.commit()
            ctx.db.refresh(appointment)
            payload = {"ok": True, "appointment": _appointment_summary(ctx, appointment)}
            return _json(payload)
        except (ValueError, BookingRuleError, IntegrityError) as exc:
            ctx.db.rollback()
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="book_appointment",
                action_type="appointment_create",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def confirm_appointment(appointment_id: str) -> str:
        """Confirm one of the current customer's pending appointments."""
        inputs = {"appointment_id": appointment_id}
        try:
            appointment_uuid = _uuid(appointment_id, "appointment_id")
            appointment = ctx.db.scalar(
                select(Appointment).where(
                    Appointment.workspace_id == ctx.workspace.id,
                    Appointment.patient_id == ctx.patient.id,
                    Appointment.id == appointment_uuid,
                )
            )
            if appointment is None:
                raise ValueError("Appointment not found for this customer.")
            if appointment.status == "confirmed":
                payload = {"ok": True, "appointment": _appointment_summary(ctx, appointment)}
                _record_action(
                    ctx,
                    tool_name="confirm_appointment",
                    action_type="appointment_confirm",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                    appointment_id=appointment.id,
                )
                return _json(payload)
            if appointment.status != "pending":
                raise BookingRuleError(
                    f"Cannot confirm an appointment with status '{appointment.status}'."
                )
            old_status = appointment.status
            appointment.status = "confirmed"
            appointment.confirmed_at = datetime.now(timezone.utc)
            _history(
                ctx,
                appointment,
                from_status=old_status,
                to_status="confirmed",
                reason="appointment_confirmed_by_ai",
            )
            ctx.db.add(
                AgentAction(
                    workspace_id=ctx.workspace.id,
                    conversation_id=ctx.conversation.id,
                    patient_id=ctx.patient.id,
                    appointment_id=appointment.id,
                    run_id=ctx.run_id,
                    tool_name="confirm_appointment",
                    action_type="appointment_confirm",
                    status="success",
                    input_json=inputs,
                    output_json={"appointment_id": str(appointment.id), "status": "confirmed"},
                )
            )
            ctx.db.commit()
            ctx.db.refresh(appointment)
            return _json({"ok": True, "appointment": _appointment_summary(ctx, appointment)})
        except (ValueError, BookingRuleError) as exc:
            ctx.db.rollback()
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="confirm_appointment",
                action_type="appointment_confirm",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def cancel_appointment(appointment_id: str, reason: str = "") -> str:
        """Cancel the current customer's appointment when clinic policy allows it.

Reason is optional. Do not make the customer provide a reason before cancellation.
If they do not give one, use "customer_requested".
Never override cancellation policy."""
        reason = reason.strip() or "customer_requested"
        inputs = {"appointment_id": appointment_id, "reason": reason}
        try:
            appointment_uuid = _uuid(appointment_id, "appointment_id")
            appointment = ctx.db.scalar(
                select(Appointment).where(
                    Appointment.workspace_id == ctx.workspace.id,
                    Appointment.patient_id == ctx.patient.id,
                    Appointment.id == appointment_uuid,
                )
            )
            if appointment is None:
                raise ValueError("Appointment not found for this customer.")
            if appointment.status == "cancelled":
                payload = {"ok": True, "appointment": _appointment_summary(ctx, appointment)}
                _record_action(
                    ctx,
                    tool_name="cancel_appointment",
                    action_type="appointment_cancel",
                    status="success",
                    input_payload=inputs,
                    output_payload=payload,
                    appointment_id=appointment.id,
                )
                return _json(payload)
            if appointment.status in {"completed", "no_show", "rescheduled"}:
                raise BookingRuleError(
                    f"Cannot cancel an appointment with status '{appointment.status}'."
                )
            now = datetime.now(timezone.utc)
            settings = get_effective_booking_settings(ctx.db, ctx.workspace.id)
            if appointment.start_at - now < timedelta(minutes=settings.cancellation_notice_minutes):
                _set_handoff(ctx)
                payload = {
                    "ok": False,
                    "requires_human": True,
                    "error": "Cancellation is inside the clinic notice window and needs staff approval.",
                }
                _record_action(
                    ctx,
                    tool_name="cancel_appointment",
                    action_type="appointment_cancel",
                    status="blocked",
                    input_payload=inputs,
                    output_payload=payload,
                    appointment_id=appointment.id,
                    error_message=payload["error"],
                )
                return _json(payload)

            old_status = appointment.status
            appointment.status = "cancelled"
            appointment.cancelled_at = now
            appointment.cancellation_reason = reason.strip() or "customer_requested_cancellation"
            _history(
                ctx,
                appointment,
                from_status=old_status,
                to_status="cancelled",
                reason=appointment.cancellation_reason,
            )
            ctx.db.add(
                AgentAction(
                    workspace_id=ctx.workspace.id,
                    conversation_id=ctx.conversation.id,
                    patient_id=ctx.patient.id,
                    appointment_id=appointment.id,
                    run_id=ctx.run_id,
                    tool_name="cancel_appointment",
                    action_type="appointment_cancel",
                    status="success",
                    input_json=inputs,
                    output_json={"appointment_id": str(appointment.id), "status": "cancelled"},
                )
            )
            ctx.db.commit()
            ctx.db.refresh(appointment)
            return _json({"ok": True, "appointment": _appointment_summary(ctx, appointment)})
        except (ValueError, BookingRuleError) as exc:
            ctx.db.rollback()
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="cancel_appointment",
                action_type="appointment_cancel",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def reschedule_appointment(
        appointment_id: str,
        start_at: str,
        branch_id: str = "",
        doctor_id: str = "",
        reason: str = "",
    ) -> str:
        """Reschedule the current customer's pending/confirmed appointment to an exact available slot."""
        inputs = {
            "appointment_id": appointment_id,
            "start_at": start_at,
            "branch_id": branch_id,
            "doctor_id": doctor_id,
            "reason": reason,
        }
        try:
            appointment_uuid = _uuid(appointment_id, "appointment_id")
            current = ctx.db.scalar(
                select(Appointment).where(
                    Appointment.workspace_id == ctx.workspace.id,
                    Appointment.patient_id == ctx.patient.id,
                    Appointment.id == appointment_uuid,
                )
            )
            if current is None:
                raise ValueError("Appointment not found for this customer.")
            if current.status not in {"pending", "confirmed"}:
                raise BookingRuleError(
                    f"Only pending or confirmed appointments can be rescheduled; current status is '{current.status}'."
                )
            requested_start = datetime.fromisoformat(start_at)
            if requested_start.tzinfo is None or requested_start.utcoffset() is None:
                raise ValueError("start_at must include the timezone offset from availability results.")
            new_branch_id = _uuid(branch_id, "branch_id") if branch_id else current.branch_id
            new_doctor_id = _uuid(doctor_id, "doctor_id") if doctor_id else current.doctor_id
            slot = find_exact_slot(
                db=ctx.db,
                workspace=ctx.workspace,
                branch_id=new_branch_id,
                service_id=current.service_id,
                doctor_id=new_doctor_id,
                requested_start_at=requested_start,
                exclude_appointment_id=current.id,
            )
            old_status = current.status
            old_start = current.start_at
            replacement = Appointment(
                workspace_id=ctx.workspace.id,
                patient_id=current.patient_id,
                branch_id=new_branch_id,
                doctor_id=new_doctor_id,
                service_id=current.service_id,
                lead_id=current.lead_id,
                created_by_user_id=None,
                rescheduled_from_appointment_id=current.id,
                status=old_status,
                source="ai",
                start_at=slot.start_at,
                end_at=slot.end_at,
                busy_start_at=slot.busy_start_at,
                busy_end_at=slot.busy_end_at,
                duration_minutes=slot.duration_minutes,
                price_minor=slot.price_minor,
                currency=slot.currency,
                customer_note=current.customer_note,
                idempotency_key=(
                    f"agent:{ctx.run_id}:reschedule:{current.id}:{new_doctor_id}:{slot.start_at.isoformat()}"
                )[:128],
                confirmed_at=datetime.now(timezone.utc) if old_status == "confirmed" else None,
            )
            current.status = "rescheduled"
            ctx.db.flush()
            ctx.db.add(replacement)
            ctx.db.flush()
            _history(
                ctx,
                current,
                from_status=old_status,
                to_status="rescheduled",
                reason=reason.strip() or "appointment_rescheduled_by_ai",
                metadata={
                    "replacement_appointment_id": str(replacement.id),
                    "old_start_at": old_start.isoformat(),
                    "new_start_at": replacement.start_at.isoformat(),
                },
            )
            _history(
                ctx,
                replacement,
                from_status=None,
                to_status=old_status,
                reason="rescheduled_from_previous_appointment_by_ai",
                metadata={"previous_appointment_id": str(current.id)},
            )
            ctx.db.add(
                AgentAction(
                    workspace_id=ctx.workspace.id,
                    conversation_id=ctx.conversation.id,
                    patient_id=ctx.patient.id,
                    appointment_id=replacement.id,
                    run_id=ctx.run_id,
                    tool_name="reschedule_appointment",
                    action_type="appointment_reschedule",
                    status="success",
                    input_json=inputs,
                    output_json={
                        "previous_appointment_id": str(current.id),
                        "replacement_appointment_id": str(replacement.id),
                    },
                )
            )
            ctx.db.commit()
            ctx.db.refresh(replacement)
            return _json({"ok": True, "appointment": _appointment_summary(ctx, replacement)})
        except (ValueError, BookingRuleError, IntegrityError) as exc:
            ctx.db.rollback()
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="reschedule_appointment",
                action_type="appointment_reschedule",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def send_email_to_customer(subject: str, body: str) -> str:
        """Queue a real transactional Gmail message to the current customer's saved email.

        Use only when the customer explicitly asks for information to be emailed to
        themselves. The recipient is always resolved from this patient's CRM profile;
        this tool cannot send to an arbitrary or third-party address. A successful
        result means the message was durably queued for the configured n8n Gmail
        worker, not that Gmail has already delivered it.
        """
        inputs = {
            "subject": subject,
            "body": body,
        }
        try:
            queued = queue_patient_email(
                ctx.db,
                workspace_id=ctx.workspace.id,
                patient=ctx.patient,
                subject=subject,
                body=body,
                sender_type="ai",
                source="tia_customer_agent",
                run_id=ctx.run_id,
            )
            payload = {
                "ok": True,
                "queued": True,
                "recipient_email": ctx.patient.email,
                "message_id": str(queued.message.id),
                "dispatch_id": str(queued.dispatch.id),
                "delivery_status": queued.dispatch.status,
            }
            _record_action(
                ctx,
                tool_name="send_email_to_customer",
                action_type="email_queue",
                status="success",
                input_payload=inputs,
                output_payload=payload,
            )
            return _json(payload)
        except OutboundCommunicationError as exc:
            payload = {"ok": False, "error": str(exc)}
            _record_action(
                ctx,
                tool_name="send_email_to_customer",
                action_type="email_queue",
                status="error",
                input_payload=inputs,
                output_payload=payload,
                error_message=str(exc),
            )
            return _json(payload)

    @tool
    def escalate_to_human(reason: str) -> str:
        """Hand the conversation to clinic staff for medical, sensitive, complaint, policy, or explicitly requested human support."""
        reason = reason.strip() or "human_handoff_requested"
        ctx.conversation.status = "pending"
        payload = {"ok": True, "handoff_required": True, "reason": reason}
        ctx.db.add(
            AgentAction(
                workspace_id=ctx.workspace.id,
                conversation_id=ctx.conversation.id,
                patient_id=ctx.patient.id,
                appointment_id=None,
                run_id=ctx.run_id,
                tool_name="escalate_to_human",
                action_type="human_handoff",
                status="success",
                input_json={"reason": reason},
                output_json=payload,
            )
        )
        ctx.db.commit()
        return _json(payload)

    return [
        get_customer_profile,
        search_services,
        list_branches,
        list_doctors,
        get_booking_options,
        get_reschedule_options,
        get_available_slots,
        get_customer_appointments,
        book_appointment,
        confirm_appointment,
        cancel_appointment,
        reschedule_appointment,
        send_email_to_customer,
        escalate_to_human,
    ]
