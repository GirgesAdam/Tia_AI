from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class AnalyticsMoneyRead(BaseModel):
    currency: str
    completed_value_minor: int
    gross_paid_minor: int
    refunded_minor: int
    recorded_paid_minor: int
    outstanding_balance_minor: int


class AnalyticsBreakdownRead(BaseModel):
    id: UUID
    name: str
    appointments: int
    completed: int
    no_show: int
    cancelled: int


class AnalyticsDailyRead(BaseModel):
    date: date
    appointments: int
    completed: int
    no_show: int
    cancelled: int
    new_patients: int


class AnalyticsOverviewRead(BaseModel):
    days: int
    timezone: str
    start_at: datetime
    end_at: datetime
    total_appointments: int
    completed_appointments: int
    no_show_appointments: int
    cancelled_appointments: int
    pending_or_confirmed_appointments: int
    attendance_rate_percent: float
    no_show_rate_percent: float
    cancellation_rate_percent: float
    new_patients: int
    conversations_started: int
    handoffs_created: int
    money: list[AnalyticsMoneyRead]
    top_services: list[AnalyticsBreakdownRead]
    top_branches: list[AnalyticsBreakdownRead]
    daily: list[AnalyticsDailyRead]
