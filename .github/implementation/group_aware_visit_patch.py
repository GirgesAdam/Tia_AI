from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_exact(path: str, old: str, new: str, expected: int = 1) -> None:
    text = read(path)
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"{path}: expected {expected} matches, found {count} for {old[:120]!r}"
        )
    write(path, text.replace(old, new))


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    text = read(path)
    start_at = text.find(start)
    if start_at < 0:
        raise SystemExit(f"{path}: missing start marker {start!r}")
    end_at = text.find(end, start_at)
    if end_at < 0:
        raise SystemExit(f"{path}: missing end marker {end!r}")
    write(path, text[:start_at] + replacement + text[end_at:])


base = "backend/app/integrations/clinic/base.py"
replace_exact(
    base,
    "    exclude_appointment_id: str | None = None\n    now: datetime | None = None\n",
    "    exclude_appointment_id: str | None = None\n"
    "    exclude_appointment_ids: tuple[str, ...] = ()\n"
    "    now: datetime | None = None\n",
)
replace_exact(
    base,
    "    laser_device_key: str | None = None\n"
    "    laser_device_name: str | None = None\n\n\n"
    "@dataclass(frozen=True)\nclass AppointmentReadResult:",
    "    laser_device_key: str | None = None\n"
    "    laser_device_name: str | None = None\n"
    "    visit_group_id: str | None = None\n\n\n"
    "@dataclass(frozen=True)\nclass AppointmentReadResult:",
)

booking = "backend/app/services/booking.py"
replace_exact(
    booking,
    "from __future__ import annotations\n\nfrom dataclasses import dataclass\n",
    "from __future__ import annotations\n\n"
    "from collections.abc import Collection\n"
    "from dataclasses import dataclass\n",
)
replace_exact(
    booking,
    "    laser_device_key: str | None = None,\n) -> tuple[str, list[SlotCandidate]]:\n",
    "    laser_device_key: str | None = None,\n"
    "    exclude_appointment_ids: Collection[UUID] = (),\n"
    ") -> tuple[str, list[SlotCandidate]]:\n",
    expected=1,
)
replace_exact(
    booking,
    "    appointment_stmt = select(Appointment).where(\n",
    "    excluded_appointment_ids = set(exclude_appointment_ids)\n"
    "    if exclude_appointment_id is not None:\n"
    "        excluded_appointment_ids.add(exclude_appointment_id)\n\n"
    "    appointment_stmt = select(Appointment).where(\n",
)
replace_exact(
    booking,
    "    if exclude_appointment_id is not None:\n"
    "        appointment_stmt = appointment_stmt.where(Appointment.id != exclude_appointment_id)\n",
    "    if excluded_appointment_ids:\n"
    "        appointment_stmt = appointment_stmt.where(\n"
    "            Appointment.id.notin_(tuple(excluded_appointment_ids))\n"
    "        )\n",
)
replace_exact(
    booking,
    "        if exclude_appointment_id is not None:\n"
    "            device_stmt = device_stmt.where(Appointment.id != exclude_appointment_id)\n",
    "        if excluded_appointment_ids:\n"
    "            device_stmt = device_stmt.where(\n"
    "                Appointment.id.notin_(tuple(excluded_appointment_ids))\n"
    "            )\n",
)
replace_exact(
    booking,
    "    laser_device_key: str | None = None,\n) -> SlotCandidate:\n",
    "    laser_device_key: str | None = None,\n"
    "    exclude_appointment_ids: Collection[UUID] = (),\n"
    ") -> SlotCandidate:\n",
    expected=1,
)
replace_exact(
    booking,
    "        exclude_appointment_id=exclude_appointment_id,\n"
    "        laser_device_key=laser_device_key,\n",
    "        exclude_appointment_id=exclude_appointment_id,\n"
    "        laser_device_key=laser_device_key,\n"
    "        exclude_appointment_ids=exclude_appointment_ids,\n",
    expected=1,
)

tia = "backend/app/integrations/clinic/tia_database.py"
replace_exact(
    tia,
    "        exclude_appointment_id = self._native_uuid(\n"
    "            request.exclude_appointment_id,\n"
    "            \"exclude_appointment_id\",\n"
    "        )\n",
    "        exclude_appointment_id = self._native_uuid(\n"
    "            request.exclude_appointment_id,\n"
    "            \"exclude_appointment_id\",\n"
    "        )\n"
    "        exclude_appointment_ids = tuple(\n"
    "            parsed\n"
    "            for item in request.exclude_appointment_ids\n"
    "            if (parsed := self._native_uuid(item, \"exclude_appointment_ids\")) is not None\n"
    "        )\n",
)
replace_exact(
    tia,
    "            exclude_appointment_id=exclude_appointment_id,\n"
    "            now=request.now,\n",
    "            exclude_appointment_id=exclude_appointment_id,\n"
    "            exclude_appointment_ids=exclude_appointment_ids,\n"
    "            now=request.now,\n",
)
replace_exact(
    tia,
    "            laser_device_name=getattr(appointment, \"laser_device_name\", None),\n"
    "        )\n",
    "            laser_device_name=getattr(appointment, \"laser_device_name\", None),\n"
    "            visit_group_id=(\n"
    "                str(appointment.visit_group_id) if appointment.visit_group_id else None\n"
    "            ),\n"
    "        )\n",
    expected=1,
)

ops = "backend/app/services/appointment_operations.py"
replace_exact(
    ops,
    "    now: datetime | None = None,\n) -> tuple[Appointment, Appointment]:\n",
    "    now: datetime | None = None,\n"
    "    exclude_appointment_ids: tuple[UUID, ...] = (),\n"
    ") -> tuple[Appointment, Appointment]:\n",
    expected=1,
)
replace_exact(
    ops,
    "            exclude_appointment_id=current.id,\n"
    "            laser_device_key=new_laser_device_key,\n",
    "            exclude_appointment_id=current.id,\n"
    "            exclude_appointment_ids=exclude_appointment_ids,\n"
    "            laser_device_key=new_laser_device_key,\n",
    expected=1,
)
replace_exact(
    ops,
    "        patient_package_id=current.patient_package_id,\n"
    "        lead_id=current.lead_id,\n",
    "        patient_package_id=current.patient_package_id,\n"
    "        visit_group_id=current.visit_group_id,\n"
    "        lead_id=current.lead_id,\n",
    expected=1,
)

grouped = Path("backend/app/services/agent_v2/grouped_visit_operations.py")
if grouped.exists():
    raise SystemExit("grouped_visit_operations.py already exists")
grouped.write_text(
    dedent(
        '''
        from __future__ import annotations

        from datetime import datetime
        from uuid import UUID

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.models.appointment import Appointment
        from app.models.workspace import Workspace
        from app.services.appointment_operations import (
            AppointmentOperationError,
            cancel_appointment_operation,
            reschedule_appointment_operation,
        )


        def _visit_members(
            db: Session,
            *,
            workspace_id: UUID,
            patient_id: UUID,
            visit_group_id: UUID,
            appointment_ids: tuple[UUID, ...],
        ) -> list[Appointment]:
            if len(appointment_ids) < 2:
                raise AppointmentOperationError("A grouped visit must contain at least two appointments.")
            rows = list(
                db.scalars(
                    select(Appointment)
                    .where(
                        Appointment.workspace_id == workspace_id,
                        Appointment.patient_id == patient_id,
                        Appointment.visit_group_id == visit_group_id,
                        Appointment.id.in_(appointment_ids),
                    )
                    .order_by(Appointment.start_at, Appointment.id)
                )
            )
            if {row.id for row in rows} != set(appointment_ids):
                raise AppointmentOperationError(
                    "The verified visit group no longer matches its appointments."
                )
            return rows


        def cancel_visit_group_operation(
            db: Session,
            *,
            workspace: Workspace,
            patient_id: UUID,
            visit_group_id: UUID,
            appointment_ids: tuple[UUID, ...],
            now: datetime | None = None,
        ) -> list[Appointment]:
            members = _visit_members(
                db,
                workspace_id=workspace.id,
                patient_id=patient_id,
                visit_group_id=visit_group_id,
                appointment_ids=appointment_ids,
            )
            cancelled: list[Appointment] = []
            with db.begin_nested():
                for member in members:
                    cancelled.append(
                        cancel_appointment_operation(
                            db,
                            workspace=workspace,
                            appointment_id=member.id,
                            changed_by_user_id=None,
                            patient_id=patient_id,
                            reason="customer_requested_visit_cancellation",
                            override_policy=False,
                            actor_is_admin=False,
                            actor_type="ai",
                            now=now,
                        )
                    )
            return cancelled


        def _uuid(value: object, field: str) -> UUID:
            try:
                return UUID(str(value))
            except (TypeError, ValueError) as exc:
                raise AppointmentOperationError(
                    f"Invalid grouped reschedule {field}."
                ) from exc


        def _aware_datetime(value: object) -> datetime:
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise AppointmentOperationError(
                    "Grouped reschedule start_at must include a timezone offset."
                )
            return parsed


        def reschedule_visit_group_operation(
            db: Session,
            *,
            workspace: Workspace,
            patient_id: UUID,
            visit_group_id: UUID,
            appointment_ids: tuple[UUID, ...],
            components: list[dict[str, object]],
            idempotency_key: str | None = None,
            now: datetime | None = None,
        ) -> list[tuple[Appointment, Appointment]]:
            members = _visit_members(
                db,
                workspace_id=workspace.id,
                patient_id=patient_id,
                visit_group_id=visit_group_id,
                appointment_ids=appointment_ids,
            )
            targets = {str(item.get("appointment_id")): item for item in components}
            if set(targets) != {str(member.id) for member in members}:
                raise AppointmentOperationError(
                    "Grouped reschedule targets do not match the verified visit."
                )

            moved: list[tuple[Appointment, Appointment]] = []
            with db.begin_nested():
                for member in members:
                    target = targets[str(member.id)]
                    replacement, previous = reschedule_appointment_operation(
                        db,
                        workspace=workspace,
                        appointment_id=member.id,
                        requested_start_at=_aware_datetime(target.get("start_at")),
                        changed_by_user_id=None,
                        branch_id=_uuid(target.get("branch_id"), "branch_id"),
                        doctor_id=_uuid(target.get("doctor_id"), "doctor_id"),
                        service_id=_uuid(target.get("service_id"), "service_id"),
                        laser_device_key=(
                            str(target["device_key"]) if target.get("device_key") else None
                        ),
                        patient_id=patient_id,
                        idempotency_key=(
                            f"{idempotency_key}:{member.id}" if idempotency_key else None
                        ),
                        actor_type="ai",
                        now=now,
                        exclude_appointment_ids=appointment_ids,
                    )
                    moved.append((replacement, previous))
            return moved
        '''
    ).lstrip(),
    encoding="utf-8",
)

read_exec = "backend/app/services/agent_v2/read_executor.py"
replace_between(
    read_exec,
    "def _appointment_payload(row: AppointmentRecord) -> dict[str, object]:\n",
    "def _appointment_matches_date(\n",
    dedent(
        '''
        def _appointment_payload(row: AppointmentRecord) -> dict[str, object]:
            try:
                tz = ZoneInfo(row.timezone)
            except Exception:
                tz = ZoneInfo("UTC")
            return {
                "appointment_id": row.appointment_id,
                "visit_group_id": row.visit_group_id,
                "status": row.status,
                "service_id": row.service_id,
                "service_name": row.service_name,
                "branch_id": row.branch_id,
                "branch_name": row.branch_name,
                "doctor_id": row.doctor_id,
                "doctor_name": row.doctor_name,
                "start_at": row.start_at.isoformat(),
                "end_at": row.end_at.isoformat(),
                "start_local": row.start_at.astimezone(tz).isoformat(),
                "end_local": row.end_at.astimezone(tz).isoformat(),
                "timezone": row.timezone,
                "price_minor": int(row.price_minor),
                "currency": row.currency,
                "payment_status": row.payment_status,
                "amount_paid_minor": row.amount_paid_minor,
                "payment_method": row.payment_method,
                "billing_context": row.billing_context,
                "patient_package_id": row.patient_package_id,
                "package_external_id": row.package_external_id,
                "laser_device_key": row.laser_device_key,
                "laser_device_name": row.laser_device_name,
            }


        def _group_appointment_rows(
            rows: list[AppointmentRecord],
        ) -> list[list[AppointmentRecord]]:
            groups: dict[str, list[AppointmentRecord]] = {}
            for row in rows:
                key = (
                    f"visit:{row.visit_group_id}"
                    if row.visit_group_id
                    else f"appointment:{row.appointment_id}"
                )
                groups.setdefault(key, []).append(row)
            return [
                sorted(group, key=lambda item: (item.start_at, item.appointment_id))
                for group in groups.values()
            ]


        def _common(values: list[str | None]) -> str | None:
            unique = {value for value in values if value is not None}
            return next(iter(unique)) if len(unique) == 1 else None


        def _visit_payload(rows: list[AppointmentRecord]) -> dict[str, object]:
            ordered = sorted(rows, key=lambda item: (item.start_at, item.appointment_id))
            statuses = {row.status for row in ordered}
            currencies = {row.currency for row in ordered}
            return {
                "visit_group_id": _common([row.visit_group_id for row in ordered]),
                "appointment_ids": [row.appointment_id for row in ordered],
                "status": next(iter(statuses)) if len(statuses) == 1 else "mixed",
                "start_at": min(row.start_at for row in ordered).isoformat(),
                "end_at": max(row.end_at for row in ordered).isoformat(),
                "branch_id": _common([row.branch_id for row in ordered]),
                "branch_name": _common([row.branch_name for row in ordered]),
                "doctor_id": _common([row.doctor_id for row in ordered]),
                "doctor_name": _common([row.doctor_name for row in ordered]),
                "currency": next(iter(currencies)) if len(currencies) == 1 else None,
                "price_minor": sum(int(row.price_minor) for row in ordered),
                "services": [
                    {
                        "appointment_id": row.appointment_id,
                        "service_id": row.service_id,
                        "service_name": row.service_name,
                        "start_at": row.start_at.isoformat(),
                        "end_at": row.end_at.isoformat(),
                        "laser_device_key": row.laser_device_key,
                        "laser_device_name": row.laser_device_name,
                    }
                    for row in ordered
                ],
            }


        '''
    ).lstrip(),
)

group_availability = dedent(
    '''
    def _read_group_reschedule_availability(
        request: ReadRequest,
        context: ReadExecutionContext,
        *,
        appointments: list[AppointmentRecord],
    ) -> tuple[ReadResult, VerificationFacts]:
        ordered = sorted(appointments, key=lambda item: (item.start_at, item.appointment_id))
        anchor = ordered[0]
        if len({row.branch_id for row in ordered}) != 1 or len({row.doctor_id for row in ordered}) != 1:
            return (
                ReadResult(kind=request.kind, ok=False, error_code="invalid_visit_group"),
                VerificationFacts(exact_slot_match_count=0),
            )

        params = dict(request.parameters)
        date_values, truncated, stop_on_first = _constraint_dates(
            params.get("date"),
            now_date=context.now.astimezone(ZoneInfo(context.workspace.timezone)).date(),
        )
        if not date_values:
            return (
                ReadResult(kind=request.kind, ok=False, error_code="missing_date"),
                VerificationFacts(),
            )

        target_branch_id = str(params.get("branch_id") or anchor.branch_id)
        target_doctor_id = str(params.get("doctor_id") or anchor.doctor_id)
        excluded_ids = tuple(row.appointment_id for row in ordered)
        adapter = _adapter(context)
        adapter.require_capability(ClinicCapability.AVAILABILITY_READ)
        slots: list[dict[str, object]] = []
        checked_dates: list[str] = []
        service_meta: dict[str, object] = {}

        for booking_date in date_values:
            checked_dates.append(booking_date.isoformat())
            anchor_availability = adapter.get_availability(
                AvailabilityRequest(
                    branch_id=target_branch_id,
                    service_id=anchor.service_id,
                    booking_date=booking_date,
                    doctor_id=target_doctor_id,
                    exclude_appointment_ids=excluded_ids,
                    now=context.now,
                    laser_device_key=anchor.laser_device_key,
                )
            )
            if not service_meta:
                service_meta = {
                    "service_id": anchor_availability.service_id,
                    "service_name": anchor_availability.service_name,
                    "branch_id": anchor_availability.branch_id,
                    "branch_name": anchor_availability.branch_name,
                    "timezone": anchor_availability.timezone,
                }
            anchor_matches = [
                slot
                for slot in anchor_availability.slots
                if _slot_matches_time(
                    slot,
                    timezone_name=anchor_availability.timezone,
                    constraint=params.get("time"),
                )
            ]
            date_matches: list[dict[str, object]] = []
            for anchor_slot in anchor_matches:
                delta = anchor_slot.start_at - anchor.start_at
                component_targets: list[dict[str, object]] = []
                group_available = True
                for row in ordered:
                    target_start = row.start_at + delta
                    if row.appointment_id == anchor.appointment_id:
                        matched_slot = anchor_slot
                    else:
                        target_date = target_start.astimezone(
                            ZoneInfo(anchor_availability.timezone)
                        ).date()
                        component_availability = adapter.get_availability(
                            AvailabilityRequest(
                                branch_id=target_branch_id,
                                service_id=row.service_id,
                                booking_date=target_date,
                                doctor_id=anchor_slot.doctor_id,
                                exclude_appointment_ids=excluded_ids,
                                now=context.now,
                                laser_device_key=row.laser_device_key,
                            )
                        )
                        matched_slot = next(
                            (
                                slot
                                for slot in component_availability.slots
                                if slot.start_at == target_start
                            ),
                            None,
                        )
                        if matched_slot is None:
                            group_available = False
                            break
                    component_target: dict[str, object] = {
                        "appointment_id": row.appointment_id,
                        "branch_id": matched_slot.branch_id,
                        "service_id": matched_slot.service_id,
                        "doctor_id": matched_slot.doctor_id,
                        "start_at": matched_slot.start_at.isoformat(),
                    }
                    if matched_slot.laser_device_key:
                        component_target["device_key"] = matched_slot.laser_device_key
                    component_targets.append(component_target)
                if group_available:
                    payload = _slot_payload(
                        anchor_slot,
                        timezone_name=anchor_availability.timezone,
                    )
                    payload.update(
                        {
                            "visit_group_id": anchor.visit_group_id,
                            "appointment_ids": list(excluded_ids),
                            "reschedule_components": component_targets,
                        }
                    )
                    date_matches.append(payload)

            unique: dict[tuple[str, str], dict[str, object]] = {}
            for slot in date_matches:
                key = (str(slot.get("doctor_id") or ""), str(slot.get("start_at") or ""))
                unique[key] = slot
            date_matches = list(unique.values())
            slots.extend(date_matches)
            if date_matches and stop_on_first:
                break

        mode, start, _end = _time_constraint(params.get("time"))
        if mode == "nearest":
            slots = _nearest_payloads(slots, anchor=start)
        exact_count = len(slots) if mode == "exact" else None
        verified: dict[str, object] = {}
        if exact_count == 1:
            slot = slots[0]
            verified = {
                "appointment_id": anchor.appointment_id,
                "appointment_ids": list(excluded_ids),
                "visit_group_id": anchor.visit_group_id,
                "branch_id": slot["branch_id"],
                "service_id": slot["service_id"],
                "doctor_id": slot["doctor_id"],
                "start_at": slot["start_at"],
                "reschedule_components": slot["reschedule_components"],
            }

        return (
            ReadResult(
                kind=request.kind,
                ok=True,
                payload={
                    **service_meta,
                    "checked_dates": checked_dates,
                    "slots": slots,
                    "matching_slot_count": len(slots),
                    "search_truncated": truncated,
                    "presentation_unit": "visit",
                },
            ),
            VerificationFacts(
                exact_slot_match_count=exact_count,
                verified_parameters=verified,
            ),
        )


    '''
).lstrip()
replace_exact(read_exec, "def _read_appointments(\n", group_availability + "def _read_appointments(\n")

replace_between(
    read_exec,
    "def _read_appointments(\n",
    "def _read_customer_profile(\n",
    dedent(
        '''
        def _read_appointments(
            request: ReadRequest,
            context: ReadExecutionContext,
            *,
            operation_type: str,
        ) -> tuple[ReadResult, VerificationFacts, list[AppointmentRecord] | None]:
            adapter = _adapter(context)
            adapter.require_capability(ClinicCapability.APPOINTMENTS_READ)
            response = adapter.get_patient_appointments(
                AppointmentReadRequest(
                    patient_id=str(context.patient.id),
                    include_past=False,
                    now=context.now,
                )
            )
            rows = list(response.appointments)
            if operation_type in {"confirm_appointment", "cancel_appointment", "reschedule"}:
                rows = [row for row in rows if row.status in _ACTIONABLE_APPOINTMENT_STATUSES]
            if operation_type == "confirm_appointment":
                rows = [row for row in rows if row.status == "pending"]

            params = request.parameters
            if params.get("appointment_id") is not None:
                rows = [
                    row for row in rows
                    if row.appointment_id == str(params["appointment_id"])
                ]
            if params.get("service_id") is not None:
                rows = [row for row in rows if row.service_id == str(params["service_id"])]
            if params.get("doctor_id") is not None:
                rows = [row for row in rows if row.doctor_id == str(params["doctor_id"])]
            if params.get("date") is not None:
                rows = [
                    row
                    for row in rows
                    if _appointment_matches_date(row, params["date"], now=context.now)
                ]

            component_scoped = (
                params.get("appointment_id") is not None
                or params.get("service_id") is not None
                or operation_type == "confirm_appointment"
            )
            logical_groups = (
                [[row] for row in rows]
                if component_scoped
                else _group_appointment_rows(rows)
            )
            selected = logical_groups[0] if len(logical_groups) == 1 else None
            verified: dict[str, object] = {}
            if selected is not None:
                anchor = selected[0]
                verified = {
                    "appointment_id": anchor.appointment_id,
                    "branch_id": anchor.branch_id,
                    "doctor_id": anchor.doctor_id,
                }
                if len(selected) == 1:
                    verified["service_id"] = anchor.service_id
                    if anchor.laser_device_key:
                        verified["device_key"] = anchor.laser_device_key
                else:
                    verified["appointment_ids"] = [row.appointment_id for row in selected]
                    if anchor.visit_group_id:
                        verified["visit_group_id"] = anchor.visit_group_id

            if operation_type == "appointment_list":
                count = None
            elif operation_type == "confirm_appointment":
                count = len(rows)
            else:
                count = len(logical_groups)
            visits = [_visit_payload(group) for group in _group_appointment_rows(rows)]
            return (
                ReadResult(
                    kind=request.kind,
                    ok=True,
                    payload={
                        "appointments": [_appointment_payload(row) for row in rows],
                        "visits": visits,
                        "visit_count": len(visits),
                        "presentation_unit": "visit",
                    },
                ),
                VerificationFacts(
                    appointment_match_count=count,
                    verified_parameters=verified,
                ),
                selected,
            )


        '''
    ).lstrip(),
)

replace_between(
    read_exec,
    "def _read_customer_history(request: ReadRequest, context: ReadExecutionContext) -> ReadResult:\n",
    "def _package_filters(\n",
    dedent(
        '''
        def _read_customer_history(
            request: ReadRequest,
            context: ReadExecutionContext,
        ) -> ReadResult:
            history = build_patient_history_context(
                context.db,
                workspace_id=context.workspace.id,
                patient=context.patient,
                recent_limit=20,
            )
            payload = history.model_dump(mode="json")
            recent = payload.get("recent_appointments")
            if isinstance(recent, list):
                grouped: dict[str, list[dict[str, object]]] = {}
                for item in recent:
                    if not isinstance(item, dict):
                        continue
                    group_id = item.get("visit_group_id")
                    appointment_id = item.get("appointment_id")
                    key = (
                        f"visit:{group_id}"
                        if group_id
                        else f"appointment:{appointment_id}"
                    )
                    grouped.setdefault(key, []).append(item)
                visits: list[dict[str, object]] = []
                for items in grouped.values():
                    ordered = sorted(
                        items,
                        key=lambda item: str(item.get("start_at") or ""),
                    )
                    statuses = {str(item.get("status") or "") for item in ordered}
                    visits.append(
                        {
                            "visit_group_id": ordered[0].get("visit_group_id"),
                            "appointment_ids": [
                                item.get("appointment_id") for item in ordered
                            ],
                            "status": (
                                next(iter(statuses)) if len(statuses) == 1 else "mixed"
                            ),
                            "start_at": min(
                                str(item.get("start_at") or "") for item in ordered
                            ),
                            "end_at": max(
                                str(item.get("end_at") or "") for item in ordered
                            ),
                            "services": [item.get("service_name") for item in ordered],
                            "branch_name": ordered[0].get("branch_name"),
                            "doctor_name": ordered[0].get("doctor_name"),
                            "price_minor": sum(
                                int(item.get("price_minor") or 0) for item in ordered
                            ),
                            "net_paid_minor": sum(
                                int(item.get("net_paid_minor") or 0) for item in ordered
                            ),
                        }
                    )
                payload["recent_visits"] = visits
                payload["recent_visit_count"] = len(visits)
                payload["presentation_unit"] = "visit"
            return ReadResult(
                kind=request.kind,
                ok=True,
                payload={"history": payload},
            )


        '''
    ).lstrip(),
)

text = read(read_exec)
start = text.find(
    "def execute_step_reads(step: PlanStep, context: ReadExecutionContext) -> ReadExecutionBundle:\n"
)
if start < 0:
    raise SystemExit("missing execute_step_reads")
new_execute = dedent(
    '''
    def execute_step_reads(
        step: PlanStep,
        context: ReadExecutionContext,
    ) -> ReadExecutionBundle:
        """Execute one planner step's verified reads without performing any write action."""
        results: list[ReadResult] = []
        verification = VerificationFacts()
        selected_appointments: list[AppointmentRecord] | None = None

        for request in step.reads:
            if request.kind == "service_catalog":
                results.append(
                    _read_service_catalog(
                        request,
                        context,
                        include_explanation=step.operation_type == "service_info",
                    )
                )
            elif request.kind == "clinic_info":
                results.append(_read_clinic_info(request, context))
            elif request.kind == "doctors":
                results.append(_read_doctors(request, context))
            elif request.kind == "appointments":
                result, verified, selected = _read_appointments(
                    request,
                    context,
                    operation_type=step.operation_type,
                )
                results.append(result)
                verification = _merge_verification(verification, verified)
                if selected is not None:
                    selected_appointments = selected
            elif request.kind == "availability":
                if (
                    step.operation_type == "reschedule"
                    and selected_appointments is not None
                    and len(selected_appointments) > 1
                ):
                    result, verified = _read_group_reschedule_availability(
                        request,
                        context,
                        appointments=selected_appointments,
                    )
                else:
                    inherited: dict[str, object] = {}
                    if step.operation_type == "reschedule" and selected_appointments:
                        appointment = selected_appointments[0]
                        inherited = {
                            "appointment_id": appointment.appointment_id,
                            "branch_id": appointment.branch_id,
                            "service_id": appointment.service_id,
                            "doctor_id": appointment.doctor_id,
                            "device_key": appointment.laser_device_key,
                            "reschedule": True,
                        }
                    result, verified = _read_availability(
                        request,
                        context,
                        inherited=inherited,
                    )
                results.append(result)
                verification = _merge_verification(verification, verified)
            elif request.kind == "customer_profile":
                results.append(_read_customer_profile(request, context))
            elif request.kind == "customer_history":
                results.append(_read_customer_history(request, context))
            elif request.kind == "customer_packages":
                results.append(_read_customer_packages(request, context))
            elif request.kind == "package_offers":
                result, verified = _read_package_offers(request, context)
                results.append(result)
                verification = _merge_verification(verification, verified)
            elif request.kind == "package_refund_quote":
                results.append(_read_package_refund_quote(request, context))
            else:
                raise ReadExecutionError(f"Unsupported V2 read kind: {request.kind}")

        return ReadExecutionBundle(results=results, verification=verification)
    '''
).lstrip()
write(read_exec, text[:start] + new_execute)

schema = "backend/app/schemas/patient_history.py"
replace_exact(
    schema,
    "class PatientHistoryAppointmentRead(BaseModel):\n    appointment_id: UUID\n",
    "class PatientHistoryAppointmentRead(BaseModel):\n"
    "    appointment_id: UUID\n"
    "    visit_group_id: UUID | None = None\n",
)
history = "backend/app/services/patient_history.py"
replace_exact(
    history,
    "                appointment_id=appointment.id,\n"
    "                status=appointment.status,\n",
    "                appointment_id=appointment.id,\n"
    "                visit_group_id=appointment.visit_group_id,\n"
    "                status=appointment.status,\n",
)

write_exec = "backend/app/services/agent_v2/write_executor.py"
replace_exact(
    write_exec,
    "from app.services.agent_v2.package_booking_policy import (\n",
    "from app.services.agent_v2.grouped_visit_operations import (\n"
    "    cancel_visit_group_operation,\n"
    "    reschedule_visit_group_operation,\n"
    ")\n"
    "from app.services.agent_v2.package_booking_policy import (\n",
)
replace_exact(
    write_exec,
    "def _datetime(parameters: dict[str, object], key: str) -> datetime:\n",
    dedent(
        '''
        def _uuid_sequence(
            parameters: dict[str, object],
            key: str,
        ) -> tuple[UUID, ...]:
            raw = parameters.get(key)
            if not isinstance(raw, (list, tuple)):
                return ()
            values: list[UUID] = []
            for item in raw:
                try:
                    values.append(item if isinstance(item, UUID) else UUID(str(item)))
                except (TypeError, ValueError) as exc:
                    raise WriteExecutionError(
                        f"Verified write has an invalid {key}."
                    ) from exc
            return tuple(values)


        def _datetime(parameters: dict[str, object], key: str) -> datetime:
        '''
    ).lstrip(),
)
replace_between(
    write_exec,
    '            elif intent.kind == "cancel_appointment":\n',
    '            elif intent.kind == "reschedule":\n',
    dedent(
        '''
                    elif intent.kind == "cancel_appointment":
                        appointment_ids = _uuid_sequence(parameters, "appointment_ids")
                        visit_group_id = _optional_uuid(parameters, "visit_group_id")
                        if len(appointment_ids) > 1 and visit_group_id is not None:
                            appointments = cancel_visit_group_operation(
                                db,
                                workspace=workspace,
                                patient_id=patient.id,
                                visit_group_id=visit_group_id,
                                appointment_ids=appointment_ids,
                            )
                            result = {
                                "ok": True,
                                "write_kind": intent.kind,
                                "appointment_ids": [str(item.id) for item in appointments],
                                "visit_group_id": str(visit_group_id),
                                "status": "cancelled",
                            }
                        else:
                            appointment = cancel_appointment_operation(
                                db,
                                workspace=workspace,
                                appointment_id=_uuid(parameters, "appointment_id"),
                                changed_by_user_id=None,
                                patient_id=patient.id,
                                reason="customer_requested_cancellation",
                                override_policy=False,
                                actor_is_admin=False,
                                actor_type="ai",
                            )
                            result = {
                                "ok": True,
                                "write_kind": intent.kind,
                                "appointment_id": str(appointment.id),
                                "status": appointment.status,
                            }
        '''
    ).rstrip()
    + "\n",
)
replace_between(
    write_exec,
    '            elif intent.kind == "reschedule":\n',
    '            elif intent.kind == "buy_package":\n',
    dedent(
        '''
                    elif intent.kind == "reschedule":
                        appointment_ids = _uuid_sequence(parameters, "appointment_ids")
                        visit_group_id = _optional_uuid(parameters, "visit_group_id")
                        raw_components = parameters.get("reschedule_components")
                        components = (
                            [dict(item) for item in raw_components if isinstance(item, dict)]
                            if isinstance(raw_components, list)
                            else []
                        )
                        if (
                            len(appointment_ids) > 1
                            and visit_group_id is not None
                            and components
                        ):
                            moved = reschedule_visit_group_operation(
                                db,
                                workspace=workspace,
                                patient_id=patient.id,
                                visit_group_id=visit_group_id,
                                appointment_ids=appointment_ids,
                                components=components,
                                idempotency_key=idempotency_key,
                            )
                            result = {
                                "ok": True,
                                "write_kind": intent.kind,
                                "appointment_ids": [
                                    str(replacement.id) for replacement, _ in moved
                                ],
                                "previous_appointment_ids": [
                                    str(previous.id) for _, previous in moved
                                ],
                                "visit_group_id": str(visit_group_id),
                                "status": moved[0][0].status if moved else "rescheduled",
                            }
                        else:
                            replacement, previous = reschedule_appointment_operation(
                                db,
                                workspace=workspace,
                                appointment_id=_uuid(parameters, "appointment_id"),
                                requested_start_at=_datetime(parameters, "start_at"),
                                changed_by_user_id=None,
                                branch_id=_uuid(parameters, "branch_id"),
                                doctor_id=_uuid(parameters, "doctor_id"),
                                service_id=_uuid(parameters, "service_id"),
                                laser_device_key=(
                                    str(parameters["device_key"])
                                    if parameters.get("device_key")
                                    else None
                                ),
                                patient_id=patient.id,
                                idempotency_key=idempotency_key,
                                actor_type="ai",
                            )
                            result = {
                                "ok": True,
                                "write_kind": intent.kind,
                                "appointment_id": str(replacement.id),
                                "previous_appointment_id": str(previous.id),
                                "status": replacement.status,
                            }
        '''
    ).rstrip()
    + "\n",
)

test_path = Path("backend/tests/test_v2_grouped_visits.py")
if test_path.exists():
    raise SystemExit("test_v2_grouped_visits.py already exists")
test_path.write_text(
    dedent(
        '''
        from __future__ import annotations

        from datetime import UTC, datetime, timedelta
        from types import SimpleNamespace
        from uuid import uuid4

        from app.integrations.clinic.base import (
            AppointmentReadResult,
            AppointmentRecord,
            AvailabilityResult,
            AvailabilitySlot,
        )
        from app.services.agent_v2.planner import ReadRequest
        from app.services.agent_v2.read_executor import (
            ReadExecutionContext,
            _read_appointments,
            _read_group_reschedule_availability,
        )


        PATIENT_ID = uuid4()
        BRANCH_ID = uuid4()
        DOCTOR_ID = uuid4()
        SERVICE_A = uuid4()
        SERVICE_B = uuid4()
        GROUP_ID = uuid4()
        APPT_A = uuid4()
        APPT_B = uuid4()
        OLD_A = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)
        OLD_B = datetime(2026, 9, 15, 7, 30, tzinfo=UTC)


        def _appointment(*, appointment_id, group_id, service_id, start_at):
            return AppointmentRecord(
                appointment_id=str(appointment_id),
                patient_id=str(PATIENT_ID),
                status="confirmed",
                service_id=str(service_id),
                service_name=f"Service {service_id}",
                branch_id=str(BRANCH_ID),
                branch_name="Main",
                doctor_id=str(DOCTOR_ID),
                doctor_name="Doctor",
                start_at=start_at,
                end_at=start_at + timedelta(minutes=30),
                timezone="Africa/Cairo",
                price_minor=10_000,
                currency="EGP",
                visit_group_id=str(group_id),
            )


        ROWS = (
            _appointment(
                appointment_id=APPT_A,
                group_id=GROUP_ID,
                service_id=SERVICE_A,
                start_at=OLD_A,
            ),
            _appointment(
                appointment_id=APPT_B,
                group_id=GROUP_ID,
                service_id=SERVICE_B,
                start_at=OLD_B,
            ),
        )


        class AppointmentAdapter:
            def require_capability(self, _capability):
                return None

            def get_patient_appointments(self, _request):
                return AppointmentReadResult(appointments=ROWS)


        def _context(adapter):
            return ReadExecutionContext(
                db=SimpleNamespace(),
                workspace=SimpleNamespace(
                    timezone="Africa/Cairo",
                    primary_branch_id=BRANCH_ID,
                    name="Clinic",
                ),
                patient=SimpleNamespace(id=PATIENT_ID),
                now=datetime(2026, 9, 13, 8, 0, tzinfo=UTC),
                adapter=adapter,
            )


        def test_general_cancel_treats_group_as_one_logical_visit():
            result, verification, selected = _read_appointments(
                ReadRequest(kind="appointments"),
                _context(AppointmentAdapter()),
                operation_type="cancel_appointment",
            )
            assert verification.appointment_match_count == 1
            assert verification.verified_parameters["visit_group_id"] == str(GROUP_ID)
            assert verification.verified_parameters["appointment_ids"] == [
                str(APPT_A),
                str(APPT_B),
            ]
            assert selected is not None and len(selected) == 2
            assert result.payload["visit_count"] == 1
            assert len(result.payload["visits"]) == 1


        def test_explicit_service_scope_keeps_one_component():
            _result, verification, selected = _read_appointments(
                ReadRequest(
                    kind="appointments",
                    parameters={"service_id": str(SERVICE_B)},
                ),
                _context(AppointmentAdapter()),
                operation_type="cancel_appointment",
            )
            assert verification.appointment_match_count == 1
            assert verification.verified_parameters["appointment_id"] == str(APPT_B)
            assert "appointment_ids" not in verification.verified_parameters
            assert selected is not None and len(selected) == 1


        class AvailabilityAdapter(AppointmentAdapter):
            def __init__(self):
                self.exclusion_sets = []

            def get_availability(self, request):
                self.exclusion_sets.append(set(request.exclude_appointment_ids))
                assert set(request.exclude_appointment_ids) == {
                    str(APPT_A),
                    str(APPT_B),
                }
                start = (
                    datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
                    if request.service_id == str(SERVICE_A)
                    else datetime(2026, 9, 15, 8, 30, tzinfo=UTC)
                )
                slot = AvailabilitySlot(
                    branch_id=str(BRANCH_ID),
                    branch_name="Main",
                    doctor_id=str(DOCTOR_ID),
                    doctor_name="Doctor",
                    service_id=request.service_id,
                    service_name="Service",
                    start_at=start,
                    end_at=start + timedelta(minutes=30),
                    duration_minutes=30,
                    price_minor=10_000,
                    currency="EGP",
                )
                return AvailabilityResult(
                    timezone="Africa/Cairo",
                    branch_id=str(BRANCH_ID),
                    branch_name="Main",
                    service_id=request.service_id,
                    service_name="Service",
                    service_duration_minutes=30,
                    service_price_minor=10_000,
                    service_currency="EGP",
                    slots=(slot,),
                )


        def test_group_reschedule_verifies_every_component_excluding_whole_old_group():
            adapter = AvailabilityAdapter()
            result, verification = _read_group_reschedule_availability(
                ReadRequest(
                    kind="availability",
                    parameters={
                        "date": {"mode": "exact", "start_date": "2026-09-15"},
                        "time": {"mode": "exact", "start_time": "11:00"},
                        "reschedule": True,
                    },
                ),
                _context(adapter),
                appointments=list(ROWS),
            )
            assert result.ok is True
            assert verification.exact_slot_match_count == 1
            components = verification.verified_parameters["reschedule_components"]
            assert [item["appointment_id"] for item in components] == [
                str(APPT_A),
                str(APPT_B),
            ]
            assert [item["start_at"] for item in components] == [
                "2026-09-15T08:00:00+00:00",
                "2026-09-15T08:30:00+00:00",
            ]
            assert len(adapter.exclusion_sets) >= 2
        '''
    ).lstrip(),
    encoding="utf-8",
)
