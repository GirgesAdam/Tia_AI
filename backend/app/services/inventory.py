from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.clinic_inventory import (
    LASER_DEVICE_KEYS,
    LASER_DEVICE_NAMES,
    AppointmentProductLine,
    ClinicProduct,
    InventoryItem,
    InventoryUsage,
    ServiceDevicePrice,
)
from app.models.service import Service
from app.schemas.inventory import (
    AppointmentProductLineRead,
    InventoryItemRead,
    LaserDevicePriceRead,
)


class InventoryOperationError(ValueError):
    pass


class InventoryNotFound(InventoryOperationError):
    pass


def is_laser_service(service: Service) -> bool:
    text = f"{service.name or ''} {service.category or ''}".casefold()
    return "laser" in text or "ليزر" in text


def list_laser_device_prices(db: Session, *, workspace_id: UUID) -> list[LaserDevicePriceRead]:
    services = list(
        db.scalars(
            select(Service).where(
                Service.workspace_id == workspace_id,
                Service.is_active.is_(True),
            ).order_by(Service.name)
        )
    )
    laser_services = [service for service in services if is_laser_service(service)]
    if not laser_services:
        return []
    rows = list(
        db.scalars(
            select(ServiceDevicePrice).where(
                ServiceDevicePrice.workspace_id == workspace_id,
                ServiceDevicePrice.service_id.in_([service.id for service in laser_services]),
                ServiceDevicePrice.is_active.is_(True),
            )
        )
    )
    by_key = {(row.service_id, row.device_key): row for row in rows}
    result: list[LaserDevicePriceRead] = []
    for service in laser_services:
        for device_key in LASER_DEVICE_KEYS:
            row = by_key.get((service.id, device_key))
            result.append(
                LaserDevicePriceRead(
                    service_id=service.id,
                    service_name=service.name,
                    device_key=device_key,
                    device_name=LASER_DEVICE_NAMES[device_key],
                    price_minor=(int(row.price_minor) if row and row.price_minor is not None else None),
                    currency=(row.currency if row else service.currency or "EGP"),
                    configured=bool(row and row.price_minor is not None),
                )
            )
    return result


def upsert_laser_device_price(
    db: Session,
    *,
    workspace_id: UUID,
    service_id: UUID,
    device_key: str,
    price_minor: int,
    currency: str,
) -> ServiceDevicePrice:
    if device_key not in LASER_DEVICE_NAMES:
        raise InventoryOperationError("Unsupported laser device.")
    service = db.scalar(
        select(Service).where(
            Service.workspace_id == workspace_id,
            Service.id == service_id,
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise InventoryNotFound("Service not found.")
    if not is_laser_service(service):
        raise InventoryOperationError("Device pricing is only available for laser services.")
    row = db.scalar(
        select(ServiceDevicePrice).where(
            ServiceDevicePrice.workspace_id == workspace_id,
            ServiceDevicePrice.service_id == service_id,
            ServiceDevicePrice.device_key == device_key,
        )
    )
    if row is None:
        row = ServiceDevicePrice(
            workspace_id=workspace_id,
            service_id=service_id,
            device_key=device_key,
            device_name=LASER_DEVICE_NAMES[device_key],
            price_minor=price_minor,
            currency=currency.upper(),
            is_active=True,
        )
        db.add(row)
    else:
        row.device_name = LASER_DEVICE_NAMES[device_key]
        row.price_minor = price_minor
        row.currency = currency.upper()
        row.is_active = True
    db.flush()
    return row


def configured_device_price(
    db: Session,
    *,
    workspace_id: UUID,
    service_id: UUID,
    device_key: str | None,
) -> ServiceDevicePrice | None:
    service = db.scalar(
        select(Service).where(
            Service.workspace_id == workspace_id,
            Service.id == service_id,
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise InventoryNotFound("Service not found.")
    if not is_laser_service(service):
        return None
    if not device_key:
        raise InventoryOperationError("Laser device choice is required.")
    if device_key not in LASER_DEVICE_NAMES:
        raise InventoryOperationError("Unsupported laser device.")
    row = db.scalar(
        select(ServiceDevicePrice).where(
            ServiceDevicePrice.workspace_id == workspace_id,
            ServiceDevicePrice.service_id == service_id,
            ServiceDevicePrice.device_key == device_key,
            ServiceDevicePrice.is_active.is_(True),
        )
    )
    if row is None or row.price_minor is None:
        raise InventoryOperationError(
            f"Price for {LASER_DEVICE_NAMES[device_key]} is not configured for this laser service."
        )
    return row


def list_products(db: Session, *, workspace_id: UUID, active_only: bool = True) -> list[ClinicProduct]:
    stmt = select(ClinicProduct).where(ClinicProduct.workspace_id == workspace_id)
    if active_only:
        stmt = stmt.where(ClinicProduct.is_active.is_(True))
    return list(db.scalars(stmt.order_by(ClinicProduct.name)))


def create_product(
    db: Session,
    *,
    workspace_id: UUID,
    name: str,
    description: str | None,
) -> ClinicProduct:
    existing = db.scalar(
        select(ClinicProduct).where(
            ClinicProduct.workspace_id == workspace_id,
            ClinicProduct.name == name,
        )
    )
    if existing is not None:
        existing.is_active = True
        if description is not None:
            existing.description = description
        db.flush()
        return existing
    row = ClinicProduct(
        workspace_id=workspace_id,
        name=name,
        description=description,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def list_appointment_products(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
) -> list[AppointmentProductLineRead]:
    rows = list(
        db.scalars(
            select(AppointmentProductLine).where(
                AppointmentProductLine.workspace_id == workspace_id,
                AppointmentProductLine.appointment_id == appointment_id,
            ).order_by(AppointmentProductLine.created_at, AppointmentProductLine.id)
        )
    )
    return [
        AppointmentProductLineRead(
            id=row.id,
            appointment_id=row.appointment_id,
            product_id=row.product_id,
            product_name=row.product_name,
            quantity=row.quantity,
            unit_price_minor=row.unit_price_minor,
            currency=row.currency,
            total_minor=int(row.quantity) * int(row.unit_price_minor),
        )
        for row in rows
    ]


def appointment_products_total_minor(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
) -> int:
    return sum(
        int(row.quantity) * int(row.unit_price_minor)
        for row in db.scalars(
            select(AppointmentProductLine).where(
                AppointmentProductLine.workspace_id == workspace_id,
                AppointmentProductLine.appointment_id == appointment_id,
            )
        )
    )


def add_appointment_product(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
    product_id: UUID,
    quantity: int,
    unit_price_minor: int,
    created_by_user_id: UUID | None,
) -> AppointmentProductLine:
    appointment = db.scalar(
        select(Appointment).where(
            Appointment.workspace_id == workspace_id,
            Appointment.id == appointment_id,
        )
    )
    if appointment is None:
        raise InventoryNotFound("Appointment not found.")
    if appointment.status in {"cancelled", "no_show", "rescheduled"}:
        raise InventoryOperationError("Products cannot be added to this appointment status.")
    product = db.scalar(
        select(ClinicProduct).where(
            ClinicProduct.workspace_id == workspace_id,
            ClinicProduct.id == product_id,
            ClinicProduct.is_active.is_(True),
        )
    )
    if product is None:
        raise InventoryNotFound("Product not found.")
    row = AppointmentProductLine(
        workspace_id=workspace_id,
        appointment_id=appointment_id,
        product_id=product.id,
        product_name=product.name,
        quantity=quantity,
        unit_price_minor=unit_price_minor,
        currency=appointment.currency,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.flush()
    return row


def delete_appointment_product(
    db: Session,
    *,
    workspace_id: UUID,
    appointment_id: UUID,
    line_id: UUID,
) -> None:
    row = db.scalar(
        select(AppointmentProductLine).where(
            AppointmentProductLine.workspace_id == workspace_id,
            AppointmentProductLine.appointment_id == appointment_id,
            AppointmentProductLine.id == line_id,
        )
    )
    if row is None:
        raise InventoryNotFound("Appointment product line not found.")
    db.delete(row)
    db.flush()


def _inventory_read(row: InventoryItem) -> InventoryItemRead:
    remaining_mg = (Decimal(row.quantity_ml) * Decimal(row.concentration_mg_per_ml)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    return InventoryItemRead(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        category=row.category,
        quantity_ml=Decimal(row.quantity_ml),
        concentration_mg_per_ml=Decimal(row.concentration_mg_per_ml),
        remaining_mg=remaining_mg,
        low_stock_threshold_ml=(Decimal(row.low_stock_threshold_ml) if row.low_stock_threshold_ml is not None else None),
        notes=row.notes,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_inventory_items(db: Session, *, workspace_id: UUID) -> list[InventoryItemRead]:
    rows = list(
        db.scalars(
            select(InventoryItem).where(
                InventoryItem.workspace_id == workspace_id,
                InventoryItem.is_active.is_(True),
            ).order_by(InventoryItem.name)
        )
    )
    return [_inventory_read(row) for row in rows]


def create_inventory_item(
    db: Session,
    *,
    workspace_id: UUID,
    name: str,
    quantity_ml: Decimal,
    concentration_mg_per_ml: Decimal,
    low_stock_threshold_ml: Decimal | None,
    notes: str | None,
) -> InventoryItemRead:
    row = InventoryItem(
        workspace_id=workspace_id,
        name=" ".join(name.split()),
        category="injectable",
        quantity_ml=quantity_ml,
        concentration_mg_per_ml=concentration_mg_per_ml,
        low_stock_threshold_ml=low_stock_threshold_ml,
        notes=notes,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return _inventory_read(row)


def add_inventory_stock(
    db: Session,
    *,
    workspace_id: UUID,
    item_id: UUID,
    quantity_ml: Decimal,
) -> InventoryItemRead:
    row = db.scalar(
        select(InventoryItem).where(
            InventoryItem.workspace_id == workspace_id,
            InventoryItem.id == item_id,
            InventoryItem.is_active.is_(True),
        ).with_for_update()
    )
    if row is None:
        raise InventoryNotFound("Inventory item not found.")
    row.quantity_ml = Decimal(row.quantity_ml) + quantity_ml
    db.flush()
    return _inventory_read(row)


def record_inventory_usage(
    db: Session,
    *,
    workspace_id: UUID,
    item_id: UUID,
    used_mg: Decimal,
    appointment_id: UUID | None,
    note: str | None,
    created_by_user_id: UUID | None,
) -> tuple[InventoryUsage, InventoryItemRead]:
    row = db.scalar(
        select(InventoryItem).where(
            InventoryItem.workspace_id == workspace_id,
            InventoryItem.id == item_id,
            InventoryItem.is_active.is_(True),
        ).with_for_update()
    )
    if row is None:
        raise InventoryNotFound("Inventory item not found.")
    concentration = Decimal(row.concentration_mg_per_ml)
    used_ml = (used_mg / concentration).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if used_ml <= 0:
        raise InventoryOperationError("Usage is too small to record at 0.001 mL precision.")
    if used_ml > Decimal(row.quantity_ml):
        raise InventoryOperationError("Used amount exceeds the remaining stock.")
    if appointment_id is not None:
        appointment = db.scalar(
            select(Appointment.id).where(
                Appointment.workspace_id == workspace_id,
                Appointment.id == appointment_id,
            )
        )
        if appointment is None:
            raise InventoryNotFound("Appointment not found.")
    row.quantity_ml = Decimal(row.quantity_ml) - used_ml
    usage = InventoryUsage(
        workspace_id=workspace_id,
        inventory_item_id=row.id,
        appointment_id=appointment_id,
        used_mg=used_mg,
        used_ml=used_ml,
        note=note,
        created_by_user_id=created_by_user_id,
    )
    db.add(usage)
    db.flush()
    return usage, _inventory_read(row)
