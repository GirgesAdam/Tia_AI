from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.doctor import Doctor
from app.models.doctor_service import DoctorService
from app.models.doctor_service_category import DoctorServiceCategory
from app.models.service import Service

SERVICE_CATEGORIES = ("laser", "dermatology", "slimming")


def normalized_service_categories(values: list[str] | tuple[str, ...] | None) -> list[str]:
    unique = sorted({str(value).strip() for value in (values or []) if str(value).strip()})
    invalid = [value for value in unique if value not in SERVICE_CATEGORIES]
    if invalid:
        raise ValueError(f"Unsupported service categories: {', '.join(invalid)}")
    return unique


def categories_from_service_ids(
    db: Session,
    *,
    workspace_id: UUID,
    service_ids: list[UUID] | None,
) -> list[str]:
    ids = set(service_ids or [])
    if not ids:
        return []
    rows = list(
        db.execute(
            select(Service.id, Service.operational_category).where(
                Service.workspace_id == workspace_id,
                Service.id.in_(ids),
                Service.is_active.is_(True),
            )
        ).all()
    )
    if {row[0] for row in rows} != ids:
        raise ValueError("One or more selected services are missing or inactive.")
    return normalized_service_categories([str(category) for _id, category in rows])


def doctor_service_categories(
    db: Session,
    *,
    workspace_id: UUID,
    doctor_id: UUID,
) -> list[str]:
    return normalized_service_categories(
        list(
            db.scalars(
                select(DoctorServiceCategory.category).where(
                    DoctorServiceCategory.workspace_id == workspace_id,
                    DoctorServiceCategory.doctor_id == doctor_id,
                )
            )
        )
    )


def sync_doctor_service_assignments(
    db: Session,
    *,
    workspace_id: UUID,
    doctor: Doctor,
    categories: list[str],
) -> set[UUID]:
    categories = normalized_service_categories(categories)

    existing_categories = list(
        db.scalars(
            select(DoctorServiceCategory).where(
                DoctorServiceCategory.workspace_id == workspace_id,
                DoctorServiceCategory.doctor_id == doctor.id,
            )
        )
    )
    existing_by_category = {row.category: row for row in existing_categories}
    for category, row in existing_by_category.items():
        if category not in categories:
            db.delete(row)
    for category in categories:
        if category not in existing_by_category:
            db.add(
                DoctorServiceCategory(
                    workspace_id=workspace_id,
                    doctor_id=doctor.id,
                    category=category,
                )
            )

    if categories:
        target_ids = set(
            db.scalars(
                select(Service.id).where(
                    Service.workspace_id == workspace_id,
                    Service.is_active.is_(True),
                    Service.operational_category.in_(categories),
                )
            )
        )
    else:
        target_ids = set()

    assignments = list(
        db.scalars(
            select(DoctorService).where(
                DoctorService.workspace_id == workspace_id,
                DoctorService.doctor_id == doctor.id,
            )
        )
    )
    by_service = {row.service_id: row for row in assignments}
    for row in assignments:
        row.is_active = row.service_id in target_ids
    for service_id in target_ids - set(by_service):
        db.add(
            DoctorService(
                workspace_id=workspace_id,
                doctor_id=doctor.id,
                service_id=service_id,
                is_active=True,
            )
        )
    return target_ids


def sync_service_doctor_assignments(
    db: Session,
    *,
    workspace_id: UUID,
    service: Service,
) -> None:
    selected_doctors = set(
        db.scalars(
            select(DoctorServiceCategory.doctor_id)
            .join(
                Doctor,
                (Doctor.workspace_id == DoctorServiceCategory.workspace_id)
                & (Doctor.id == DoctorServiceCategory.doctor_id),
            )
            .where(
                DoctorServiceCategory.workspace_id == workspace_id,
                DoctorServiceCategory.category == service.operational_category,
                Doctor.is_active.is_(True),
            )
        )
    )
    assignments = list(
        db.scalars(
            select(DoctorService).where(
                DoctorService.workspace_id == workspace_id,
                DoctorService.service_id == service.id,
            )
        )
    )
    by_doctor = {row.doctor_id: row for row in assignments}
    active_targets = selected_doctors if service.is_active else set()
    for row in assignments:
        row.is_active = row.doctor_id in active_targets
    for doctor_id in active_targets - set(by_doctor):
        db.add(
            DoctorService(
                workspace_id=workspace_id,
                doctor_id=doctor_id,
                service_id=service.id,
                is_active=True,
            )
        )
