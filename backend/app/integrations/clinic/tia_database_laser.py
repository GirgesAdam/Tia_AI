from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from sqlalchemy import func, select

from app.integrations.clinic.base import (
    AppointmentMutationResult,
    AppointmentRecord,
    AvailabilityRequest,
    AvailabilityResult,
    CreateAppointmentRequest,
    RescheduleAppointmentRequest,
)
from app.integrations.clinic.tia_database import TiaDatabaseClinicAdapter
from app.models.appointment import Appointment
from app.models.clinic_inventory import ServiceDevicePrice
from app.models.service import Service
from app.services.booking import BookingRuleError
from app.services.inventory import (
    InventoryOperationError,
    configured_device_price,
    is_laser_service,
    list_laser_device_prices,
)


class TiaDatabaseLaserClinicAdapter(TiaDatabaseClinicAdapter):
    """Native adapter with the clinic's two laser-device price variants.

    The parent adapter remains the source for scheduling, patient ownership,
    package rules, writes and audit events. This extension only adds a required
    device choice for laser services and persists the verified device price/name.
    """

    def catalog_revision(self):
        base = super().catalog_revision()
        row = self.db.execute(
            select(
                func.count(ServiceDevicePrice.id),
                func.max(ServiceDevicePrice.updated_at),
            ).where(ServiceDevicePrice.workspace_id == self.workspace.id)
        ).one()
        return (*base, *tuple(row)) if isinstance(base, tuple) else (base, *tuple(row))

    def build_catalog(self):
        catalog = super().build_catalog()
        prices = list_laser_device_prices(self.db, workspace_id=self.workspace.id)
        by_service: dict[str, list[dict[str, object]]] = {}
        for item in prices:
            by_service.setdefault(str(item.service_id), []).append(
                {
                    "device_key": item.device_key,
                    "device_name": item.device_name,
                    "price_minor": item.price_minor,
                    "currency": item.currency,
                    "configured": item.configured,
                }
            )
        services = catalog.get("services")
        if isinstance(services, list):
            for service in services:
                if not isinstance(service, dict):
                    continue
                service_id = str(service.get("service_id") or service.get("id") or "")
                if service_id in by_service:
                    service["laser_devices"] = by_service[service_id]
        return catalog

    def _device_price(self, *, service_id: UUID, device_key: str | None):
        try:
            return configured_device_price(
                self.db,
                workspace_id=self.workspace.id,
                service_id=service_id,
                device_key=device_key,
            )
        except InventoryOperationError as exc:
            raise BookingRuleError(str(exc)) from exc

    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        service_id = self._native_uuid(request.service_id, "service_id")
        assert service_id is not None
        device_price = self._device_price(
            service_id=service_id,
            device_key=request.laser_device_key,
        )
        result = super().get_availability(request)
        if device_price is None:
            return result
        return replace(
            result,
            service_price_minor=int(device_price.price_minor or 0),
            service_currency=device_price.currency,
            slots=tuple(
                replace(
                    slot,
                    price_minor=int(device_price.price_minor or 0),
                    currency=device_price.currency,
                    laser_device_key=device_price.device_key,
                    laser_device_name=device_price.device_name,
                )
                for slot in result.slots
            ),
        )

    def _appointment_record(self, *, appointment_id: UUID) -> AppointmentRecord:
        record = super()._appointment_record(appointment_id=appointment_id)
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None or appointment.workspace_id != self.workspace.id:
            return record
        return replace(
            record,
            laser_device_key=appointment.laser_device_key,
            laser_device_name=appointment.laser_device_name,
        )

    def create_appointment(
        self, request: CreateAppointmentRequest
    ) -> AppointmentMutationResult:
        service_id = self._native_uuid(request.service_id, "service_id")
        assert service_id is not None
        device_price = self._device_price(
            service_id=service_id,
            device_key=request.laser_device_key,
        )
        result = super().create_appointment(request)
        if device_price is None:
            return result
        appointment_id = UUID(result.appointment.appointment_id)
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None:
            raise BookingRuleError("Appointment disappeared before laser device persistence.")
        appointment.laser_device_key = device_price.device_key
        appointment.laser_device_name = device_price.device_name
        appointment.price_minor = int(device_price.price_minor or 0)
        appointment.currency = device_price.currency
        self.db.flush()
        return AppointmentMutationResult(
            appointment=self._appointment_record(appointment_id=appointment.id)
        )

    def reschedule_appointment(
        self, request: RescheduleAppointmentRequest
    ) -> AppointmentMutationResult:
        appointment_id = self._native_uuid(request.appointment_id, "appointment_id")
        patient_id = self._native_uuid(request.patient_id, "patient_id")
        assert appointment_id is not None
        assert patient_id is not None
        current = self._patient_appointment(
            patient_id=patient_id,
            appointment_id=appointment_id,
        )
        current_device_key = current.laser_device_key
        result = super().reschedule_appointment(request)

        replacement_id = UUID(result.appointment.appointment_id)
        replacement = self.db.get(Appointment, replacement_id)
        if replacement is None:
            raise BookingRuleError("Replacement appointment not found.")
        service = self.db.get(Service, replacement.service_id)
        if service is None or service.workspace_id != self.workspace.id:
            raise BookingRuleError("Replacement service not found.")

        if not is_laser_service(service):
            replacement.laser_device_key = None
            replacement.laser_device_name = None
            self.db.flush()
            return AppointmentMutationResult(
                appointment=self._appointment_record(appointment_id=replacement.id),
                previous_appointment_id=result.previous_appointment_id,
            )

        device_price = self._device_price(
            service_id=replacement.service_id,
            device_key=current_device_key,
        )
        if device_price is None:
            raise BookingRuleError("Laser device choice is required for the replacement appointment.")
        replacement.laser_device_key = device_price.device_key
        replacement.laser_device_name = device_price.device_name
        replacement.price_minor = int(device_price.price_minor or 0)
        replacement.currency = device_price.currency
        self.db.flush()
        return AppointmentMutationResult(
            appointment=self._appointment_record(appointment_id=replacement.id),
            previous_appointment_id=result.previous_appointment_id,
        )
