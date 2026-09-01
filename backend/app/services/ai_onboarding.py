from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.onboarding_planner import plan_onboarding_turn
from app.core.doctor_names import normalize_doctor_name_parts
from app.models.booking_settings import BookingSettings
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.doctor_branch import DoctorBranch
from app.models.doctor_service import DoctorService
from app.models.onboarding_ai_event import OnboardingAIEvent
from app.models.onboarding_ai_session import OnboardingAISession
from app.models.service import Service
from app.models.staff import Staff
from app.models.user import User
from app.models.working_hours import BranchWorkingHour, DoctorWorkingHour
from app.models.workspace import Workspace
from app.schemas.onboarding_ai import (
    OnboardingAIResponse,
    OnboardingPlan,
    OnboardingTurnDecision,
)

SESSION_TTL_HOURS = 24


class OnboardingSessionConflictError(RuntimeError):
    pass


class OnboardingPlanValidationError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Onboarding plan is not executable.")
        self.errors = errors


class OnboardingExecutionError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _event(
    db: Session,
    *,
    session: OnboardingAISession,
    event_type: str,
    actor_type: str,
    user_id: UUID | None,
    content: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        OnboardingAIEvent(
            workspace_id=session.workspace_id,
            session_id=session.id,
            user_id=user_id,
            event_type=event_type,
            actor_type=actor_type,
            state_version=session.version,
            content=content,
            event_metadata=metadata or {},
        )
    )


def _expire_if_needed(db: Session, session: OnboardingAISession) -> None:
    if session.is_active and session.expires_at <= _now():
        session.status = "expired"
        session.is_active = False
        session.version += 1
        _event(
            db,
            session=session,
            event_type="expired",
            actor_type="system",
            user_id=None,
        )
        db.commit()


def get_or_create_session(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: UUID | None,
) -> OnboardingAISession:
    if session_id is not None:
        session = db.scalar(
            select(OnboardingAISession).where(
                OnboardingAISession.id == session_id,
                OnboardingAISession.workspace_id == workspace.id,
                OnboardingAISession.created_by_user_id == user.id,
            )
        )
        if session is None:
            raise OnboardingSessionConflictError("Onboarding session not found.")
        _expire_if_needed(db, session)
        if not session.is_active:
            raise OnboardingSessionConflictError(f"Onboarding session is {session.status}.")
        return session

    existing = db.scalar(
        select(OnboardingAISession).where(
            OnboardingAISession.workspace_id == workspace.id,
            OnboardingAISession.created_by_user_id == user.id,
            OnboardingAISession.is_active.is_(True),
        )
    )
    if existing is not None:
        _expire_if_needed(db, existing)
        if existing.is_active:
            return existing

    now = _now()
    session = OnboardingAISession(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        status="drafting",
        is_active=True,
        plan={},
        plan_summary={},
        missing_information=[],
        last_decision={},
        execution_result={},
        version=1,
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
        last_turn_at=now,
    )
    db.add(session)
    db.flush()
    _event(
        db,
        session=session,
        event_type="started",
        actor_type="system",
        user_id=user.id,
    )
    db.commit()
    db.refresh(session)
    return session


def _recent_history(db: Session, session: OnboardingAISession) -> list[dict]:
    rows = list(
        db.scalars(
            select(OnboardingAIEvent)
            .where(
                OnboardingAIEvent.session_id == session.id,
                OnboardingAIEvent.event_type.in_(("message", "plan_proposed", "plan_revised")),
            )
            .order_by(OnboardingAIEvent.created_at.desc())
            .limit(10)
        )
    )
    rows.reverse()
    return [
        {
            "actor": row.actor_type,
            "event": row.event_type,
            "content": row.content,
        }
        for row in rows
        if row.content
    ]


def _current_setup_snapshot(db: Session, workspace_id: UUID) -> dict:
    branches = list(
        db.scalars(select(Branch).where(Branch.workspace_id == workspace_id).order_by(Branch.name))
    )
    services = list(
        db.scalars(
            select(Service).where(Service.workspace_id == workspace_id).order_by(Service.name)
        )
    )
    staff = list(
        db.scalars(
            select(Staff)
            .where(Staff.workspace_id == workspace_id)
            .order_by(Staff.first_name, Staff.last_name)
        )
    )
    doctors = list(
        db.scalars(
            select(Doctor).where(Doctor.workspace_id == workspace_id).order_by(Doctor.created_at)
        )
    )
    staff_by_id = {row.id: row for row in staff}
    return {
        "branches": [
            {
                "name": row.name,
                "code": row.code,
                "city": row.city,
                "timezone": row.timezone,
                "active": row.is_active,
            }
            for row in branches
        ],
        "services": [
            {
                "name": row.name,
                "slug": row.slug,
                "duration_minutes": row.duration_minutes,
                "price_minor": row.price_minor,
                "currency": row.currency,
                "active": row.is_active,
            }
            for row in services
        ],
        "doctors": [
            {
                "name": (
                    f"{staff_by_id[row.staff_id].first_name} {staff_by_id[row.staff_id].last_name}"
                ).strip()
                if row.staff_id in staff_by_id
                else "Doctor",
                "specialization": row.specialization,
                "booking_enabled": row.booking_enabled,
                "active": row.is_active,
            }
            for row in doctors
        ],
        "booking_settings_exists": db.scalar(
            select(BookingSettings.id).where(BookingSettings.workspace_id == workspace_id)
        )
        is not None,
    }


def validate_plan(plan: OnboardingPlan) -> list[str]:
    errors: list[str] = []

    def duplicates(values: list[str]) -> set[str]:
        seen: set[str] = set()
        dup: set[str] = set()
        for value in values:
            if value in seen:
                dup.add(value)
            seen.add(value)
        return dup

    branch_keys = [row.key for row in plan.branches]
    service_keys = [row.key for row in plan.services]
    doctor_keys = [row.key for row in plan.doctors]

    for label, values in (
        ("branch key", branch_keys),
        ("branch code", [row.code for row in plan.branches]),
        ("service key", service_keys),
        ("service slug", [row.slug for row in plan.services]),
        ("doctor key", doctor_keys),
    ):
        for value in sorted(duplicates(values)):
            errors.append(f"Duplicate {label}: {value}")

    branch_set = set(branch_keys)
    service_set = set(service_keys)

    for doctor in plan.doctors:
        for key in doctor.branch_keys:
            if key not in branch_set:
                errors.append(f"Doctor {doctor.key} references unknown branch key {key}.")
        for key in doctor.service_keys:
            if key not in service_set:
                errors.append(f"Doctor {doctor.key} references unknown service key {key}.")
        if (
            doctor.primary_branch_key is not None
            and doctor.primary_branch_key not in doctor.branch_keys
        ):
            errors.append(f"Doctor {doctor.key} primary branch must be in branch_keys.")
        if doctor.apply_working_hours:
            for hours in doctor.working_hours:
                if hours.branch_key not in doctor.branch_keys:
                    errors.append(
                        f"Doctor {doctor.key} working hours reference an "
                        f"unassigned branch {hours.branch_key}."
                    )

    has_change = bool(plan.branches or plan.services or plan.doctors or plan.booking_settings.apply)
    if not has_change:
        errors.append("Plan does not contain any configuration change.")

    return errors


def _summary(plan: OnboardingPlan) -> dict:
    return {
        "branches": len(plan.branches),
        "services": len(plan.services),
        "doctors": len(plan.doctors),
        "branch_schedules": sum(1 for row in plan.branches if row.apply_working_hours),
        "doctor_schedules": sum(
            len(row.working_hours) for row in plan.doctors if row.apply_working_hours
        ),
        "booking_settings": plan.booking_settings.apply,
    }


def _assert_version(
    session: OnboardingAISession,
    expected_version: int | None,
) -> None:
    if expected_version is not None and session.version != expected_version:
        raise OnboardingSessionConflictError(
            f"Onboarding session version conflict: "
            f"expected {expected_version}, current {session.version}."
        )


def _response(
    session: OnboardingAISession,
    *,
    assistant_message: str,
    capabilities: list[str] | None = None,
    readiness_refresh_required: bool = False,
) -> OnboardingAIResponse:
    plan = OnboardingPlan.model_validate(session.plan) if session.plan else None
    return OnboardingAIResponse(
        session_id=session.id,
        status=session.status,
        version=session.version,
        assistant_message=assistant_message,
        capabilities=capabilities or [],
        missing_information=list(session.missing_information or []),
        plan=plan,
        plan_summary=dict(session.plan_summary or {}),
        execution_result=dict(session.execution_result or {}),
        requires_confirmation=session.status == "awaiting_confirmation",
        readiness_refresh_required=readiness_refresh_required,
    )


def _set_plan(
    db: Session,
    *,
    session: OnboardingAISession,
    user: User,
    decision: OnboardingTurnDecision,
) -> OnboardingAIResponse:
    errors = validate_plan(decision.plan)
    session.last_turn_at = _now()
    session.last_decision = decision.model_dump(mode="json")
    session.version += 1

    if errors:
        session.status = "drafting"
        session.plan = decision.plan.model_dump(mode="json")
        session.plan_summary = _summary(decision.plan)
        session.missing_information = list(dict.fromkeys([*decision.missing_information, *errors]))
        event_type = "plan_revised" if session.plan else "plan_proposed"
        _event(
            db,
            session=session,
            event_type=event_type,
            actor_type="planner",
            user_id=user.id,
            content=decision.assistant_message,
            metadata={"validation_errors": errors},
        )
        db.commit()
        db.refresh(session)
        return _response(
            session,
            assistant_message=decision.assistant_message,
            capabilities=decision.capabilities,
        )

    previous_plan = bool(session.plan)
    session.status = "awaiting_confirmation"
    session.plan = decision.plan.model_dump(mode="json")
    session.plan_summary = _summary(decision.plan)
    session.missing_information = decision.missing_information
    _event(
        db,
        session=session,
        event_type="plan_revised" if previous_plan else "plan_proposed",
        actor_type="planner",
        user_id=user.id,
        content=decision.assistant_message,
        metadata={"summary": session.plan_summary},
    )
    db.commit()
    db.refresh(session)
    return _response(
        session,
        assistant_message=decision.assistant_message,
        capabilities=decision.capabilities,
    )


def _upsert_branch(
    db: Session,
    workspace_id: UUID,
    item,
) -> Branch:
    row = db.scalar(
        select(Branch).where(
            Branch.workspace_id == workspace_id,
            Branch.code == item.code,
        )
    )
    values = item.model_dump(exclude={"key", "apply_working_hours", "working_hours"})
    if row is None:
        row = Branch(workspace_id=workspace_id, **values)
        db.add(row)
        db.flush()
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.is_active = True

    if item.apply_working_hours:
        db.execute(
            delete(BranchWorkingHour).where(
                BranchWorkingHour.workspace_id == workspace_id,
                BranchWorkingHour.branch_id == row.id,
            )
        )
        db.add_all(
            [
                BranchWorkingHour(
                    workspace_id=workspace_id,
                    branch_id=row.id,
                    weekday=interval.weekday,
                    start_time=interval.start_time,
                    end_time=interval.end_time,
                )
                for interval in item.working_hours
            ]
        )
    return row


def _upsert_service(db: Session, workspace_id: UUID, item) -> Service:
    row = db.scalar(
        select(Service).where(
            Service.workspace_id == workspace_id,
            Service.slug == item.slug,
        )
    )
    values = item.model_dump(exclude={"key"})
    if row is None:
        row = Service(workspace_id=workspace_id, **values)
        db.add(row)
        db.flush()
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.is_active = True
    return row


def _find_staff(
    db: Session,
    workspace_id: UUID,
    item,
    *,
    first_name: str,
    last_name: str,
) -> Staff | None:
    if item.email:
        row = db.scalar(
            select(Staff).where(
                Staff.workspace_id == workspace_id,
                func.lower(Staff.email) == item.email.lower(),
            )
        )
        if row is not None:
            return row
    return db.scalar(
        select(Staff).where(
            Staff.workspace_id == workspace_id,
            func.lower(Staff.first_name) == first_name.lower(),
            func.lower(Staff.last_name) == last_name.lower(),
        )
    )


def _upsert_doctor(
    db: Session,
    workspace_id: UUID,
    item,
) -> tuple[Staff, Doctor]:
    first_name, last_name = normalize_doctor_name_parts(item.first_name, item.last_name)
    staff = _find_staff(
        db, workspace_id, item, first_name=first_name, last_name=last_name
    )
    if staff is None:
        staff = Staff(
            workspace_id=workspace_id,
            user_id=None,
            first_name=first_name,
            last_name=last_name,
            email=item.email,
            phone=item.phone,
            job_title="doctor",
            is_active=True,
        )
        db.add(staff)
        db.flush()
    else:
        staff.first_name = first_name
        staff.last_name = last_name
        staff.email = item.email
        staff.phone = item.phone
        staff.job_title = "doctor"
        staff.is_active = True

    doctor = db.scalar(
        select(Doctor).where(
            Doctor.workspace_id == workspace_id,
            Doctor.staff_id == staff.id,
        )
    )
    if doctor is None:
        doctor = Doctor(
            workspace_id=workspace_id,
            staff_id=staff.id,
            specialization=item.specialization,
            license_number=item.license_number,
            bio=None,
            booking_enabled=True,
            is_active=True,
        )
        db.add(doctor)
        db.flush()
    else:
        doctor.specialization = item.specialization
        doctor.license_number = item.license_number
        doctor.booking_enabled = True
        doctor.is_active = True
    return staff, doctor


def execute_plan(
    db: Session,
    *,
    session: OnboardingAISession,
    user: User,
    expected_version: int | None,
) -> OnboardingAIResponse:
    _assert_version(session, expected_version)
    if session.status == "completed":
        return _response(
            session,
            assistant_message="الخطة دي اتنفذت بالفعل.",
            readiness_refresh_required=True,
        )
    if session.status != "awaiting_confirmation":
        raise OnboardingSessionConflictError("Onboarding plan is not awaiting confirmation.")

    plan = OnboardingPlan.model_validate(session.plan)
    errors = validate_plan(plan)
    if errors:
        raise OnboardingPlanValidationError(errors)

    session.status = "executing"
    session.version += 1
    _event(
        db,
        session=session,
        event_type="confirmed",
        actor_type="admin",
        user_id=user.id,
        metadata={"summary": _summary(plan)},
    )

    try:
        branch_by_key: dict[str, Branch] = {}
        for item in plan.branches:
            branch_by_key[item.key] = _upsert_branch(db, session.workspace_id, item)
        db.flush()

        service_by_key: dict[str, Service] = {}
        for item in plan.services:
            service_by_key[item.key] = _upsert_service(db, session.workspace_id, item)
        db.flush()

        doctor_results: list[dict] = []
        for item in plan.doctors:
            staff, doctor = _upsert_doctor(db, session.workspace_id, item)
            db.flush()

            for branch_key in item.branch_keys:
                branch = branch_by_key[branch_key]
                assignment = db.scalar(
                    select(DoctorBranch).where(
                        DoctorBranch.workspace_id == session.workspace_id,
                        DoctorBranch.doctor_id == doctor.id,
                        DoctorBranch.branch_id == branch.id,
                    )
                )
                is_primary = branch_key == item.primary_branch_key
                if assignment is None:
                    assignment = DoctorBranch(
                        workspace_id=session.workspace_id,
                        doctor_id=doctor.id,
                        branch_id=branch.id,
                        is_primary=is_primary,
                        is_active=True,
                    )
                    db.add(assignment)
                else:
                    assignment.is_primary = is_primary
                    assignment.is_active = True

            if item.primary_branch_key is not None:
                primary_id = branch_by_key[item.primary_branch_key].id
                other_assignments = list(
                    db.scalars(
                        select(DoctorBranch).where(
                            DoctorBranch.workspace_id == session.workspace_id,
                            DoctorBranch.doctor_id == doctor.id,
                            DoctorBranch.branch_id != primary_id,
                            DoctorBranch.is_primary.is_(True),
                        )
                    )
                )
                for assignment in other_assignments:
                    assignment.is_primary = False

            for service_key in item.service_keys:
                service = service_by_key[service_key]
                assignment = db.scalar(
                    select(DoctorService).where(
                        DoctorService.workspace_id == session.workspace_id,
                        DoctorService.doctor_id == doctor.id,
                        DoctorService.service_id == service.id,
                    )
                )
                if assignment is None:
                    db.add(
                        DoctorService(
                            workspace_id=session.workspace_id,
                            doctor_id=doctor.id,
                            service_id=service.id,
                            custom_duration_minutes=None,
                            custom_price_minor=None,
                            is_active=True,
                        )
                    )
                else:
                    assignment.is_active = True

            if item.apply_working_hours:
                for hours in item.working_hours:
                    branch = branch_by_key[hours.branch_key]
                    db.execute(
                        delete(DoctorWorkingHour).where(
                            DoctorWorkingHour.workspace_id == session.workspace_id,
                            DoctorWorkingHour.doctor_id == doctor.id,
                            DoctorWorkingHour.branch_id == branch.id,
                        )
                    )
                    db.add_all(
                        [
                            DoctorWorkingHour(
                                workspace_id=session.workspace_id,
                                doctor_id=doctor.id,
                                branch_id=branch.id,
                                weekday=interval.weekday,
                                start_time=interval.start_time,
                                end_time=interval.end_time,
                            )
                            for interval in hours.intervals
                        ]
                    )

            doctor_results.append(
                {
                    "doctor_id": str(doctor.id),
                    "staff_id": str(staff.id),
                    "name": f"{staff.first_name} {staff.last_name}".strip(),
                }
            )

        if plan.booking_settings.apply:
            values = plan.booking_settings.model_dump(exclude={"apply"})
            settings = db.scalar(
                select(BookingSettings).where(BookingSettings.workspace_id == session.workspace_id)
            )
            if settings is None:
                settings = BookingSettings(
                    workspace_id=session.workspace_id,
                    **values,
                )
                db.add(settings)
            else:
                for key, value in values.items():
                    setattr(settings, key, value)

        db.flush()
        result = {
            "branches": [
                {
                    "id": str(branch_by_key[item.key].id),
                    "name": branch_by_key[item.key].name,
                }
                for item in plan.branches
            ],
            "services": [
                {
                    "id": str(service_by_key[item.key].id),
                    "name": service_by_key[item.key].name,
                }
                for item in plan.services
            ],
            "doctors": doctor_results,
            "booking_settings_applied": plan.booking_settings.apply,
        }
        session.status = "completed"
        session.is_active = False
        session.completed_at = _now()
        session.execution_result = result
        session.version += 1
        _event(
            db,
            session=session,
            event_type="write_completed",
            actor_type="system",
            user_id=user.id,
            metadata=result,
        )
        db.commit()
        db.refresh(session)
    except IntegrityError as exc:
        db.rollback()
        raise OnboardingExecutionError(
            "Clinic configuration conflicted with existing data."
        ) from exc
    except Exception:
        db.rollback()
        raise

    return _response(
        session,
        assistant_message=(
            "تمام، نفذت إعدادات العيادة فعليًا. "
            "حدّثت الفروع والخدمات والدكاترة والمواعيد وإعدادات الحجز "
            "حسب الخطة المعتمدة."
        ),
        readiness_refresh_required=True,
    )


def process_onboarding_message(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    message: str,
    session_id: UUID | None,
    expected_version: int | None,
) -> OnboardingAIResponse:
    session = get_or_create_session(
        db,
        workspace=workspace,
        user=user,
        session_id=session_id,
    )
    _assert_version(session, expected_version)

    session.last_turn_at = _now()
    _event(
        db,
        session=session,
        event_type="message",
        actor_type="admin",
        user_id=user.id,
        content=message,
    )
    db.commit()
    db.refresh(session)

    decision = plan_onboarding_turn(
        message=message,
        current_setup=_current_setup_snapshot(db, workspace.id),
        stored_plan=dict(session.plan or {}),
        recent_history=_recent_history(db, session),
    )

    if decision.action == "confirm":
        if not session.plan:
            session.version += 1
            session.status = "drafting"
            session.missing_information = ["مفيش خطة محفوظة للتأكيد. اشرح إعدادات العيادة الأول."]
            session.last_decision = decision.model_dump(mode="json")
            db.commit()
            db.refresh(session)
            return _response(
                session,
                assistant_message=("محتاجين نكوّن خطة إعداد الأول قبل ما أنفذ أي تعديل."),
                capabilities=decision.capabilities,
            )
        return execute_plan(
            db,
            session=session,
            user=user,
            expected_version=session.version,
        )

    if decision.action == "cancel":
        session.status = "cancelled"
        session.is_active = False
        session.cancelled_at = _now()
        session.last_decision = decision.model_dump(mode="json")
        session.version += 1
        _event(
            db,
            session=session,
            event_type="cancelled",
            actor_type="admin",
            user_id=user.id,
            content=decision.assistant_message,
        )
        db.commit()
        db.refresh(session)
        return _response(
            session,
            assistant_message=decision.assistant_message,
            capabilities=decision.capabilities,
        )

    if decision.action in {"propose", "revise"}:
        return _set_plan(
            db,
            session=session,
            user=user,
            decision=decision,
        )

    session.status = "drafting"
    session.last_decision = decision.model_dump(mode="json")
    session.missing_information = decision.missing_information
    session.version += 1
    _event(
        db,
        session=session,
        event_type="plan_revised",
        actor_type="planner",
        user_id=user.id,
        content=decision.assistant_message,
        metadata={"clarification": True},
    )
    db.commit()
    db.refresh(session)
    return _response(
        session,
        assistant_message=decision.assistant_message,
        capabilities=decision.capabilities,
    )


def cancel_session(
    db: Session,
    *,
    session: OnboardingAISession,
    user: User,
    expected_version: int,
) -> OnboardingAIResponse:
    _assert_version(session, expected_version)
    session.status = "cancelled"
    session.is_active = False
    session.cancelled_at = _now()
    session.version += 1
    _event(
        db,
        session=session,
        event_type="cancelled",
        actor_type="admin",
        user_id=user.id,
    )
    db.commit()
    db.refresh(session)
    return _response(
        session,
        assistant_message="ألغيت خطة الإعداد الحالية ومفيش أي تعديل اتنفذ.",
    )
