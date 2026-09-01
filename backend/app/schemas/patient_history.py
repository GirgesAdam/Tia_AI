from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PatientHistoryMoneyRead(BaseModel):
    currency: str
    gross_paid_minor: int
    refunded_minor: int
    net_paid_minor: int


class PatientServiceHistoryRead(BaseModel):
    service_id: UUID
    service_name: str
    completed_visits: int
    first_completed_at: datetime | None = None
    last_completed_at: datetime | None = None


class PatientHistoryAppointmentRead(BaseModel):
    appointment_id: UUID
    status: str
    start_at: datetime
    end_at: datetime
    service_name: str
    branch_name: str
    doctor_name: str
    price_minor: int
    currency: str
    net_paid_minor: int


class PatientHistoryProfileRead(BaseModel):
    patient_id: UUID
    first_name: str
    last_name: str | None = None
    phone: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    source_created_at: datetime | None = None
    tia_created_at: datetime
    effective_first_seen_at: datetime


class PatientHistoryContextRead(BaseModel):
    profile: PatientHistoryProfileRead
    first_clinic_activity_at: datetime | None = None
    last_clinic_activity_at: datetime | None = None
    total_appointments: int
    completed_appointments: int
    cancelled_appointments: int
    no_show_appointments: int
    money: list[PatientHistoryMoneyRead] = Field(default_factory=list)
    services: list[PatientServiceHistoryRead] = Field(default_factory=list)
    recent_appointments: list[PatientHistoryAppointmentRead] = Field(default_factory=list)


class HistoricalAnalyticsServiceRead(BaseModel):
    service_id: UUID
    service_name: str
    completed_appointments: int
    unique_patients: int


class HistoricalAnalyticsRead(BaseModel):
    data_start_at: datetime | None = None
    data_end_at: datetime | None = None
    total_patients: int
    repeat_patients: int
    repeat_patient_rate_percent: float
    total_appointments: int
    completed_appointments: int
    money: list[PatientHistoryMoneyRead] = Field(default_factory=list)
    top_services: list[HistoricalAnalyticsServiceRead] = Field(default_factory=list)
