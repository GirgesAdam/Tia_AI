from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


OperationalSeverity = Literal["pass", "warn", "fail"]
OperationalStatus = Literal["ready", "degraded", "not_ready"]


class OperationalCheck(BaseModel):
    key: str
    severity: OperationalSeverity
    message: str
    value: int | str | bool | None = None
    details: dict = Field(default_factory=dict)


class WorkspaceOperationalReadiness(BaseModel):
    status: OperationalStatus
    workspace_id: str
    checks: list[OperationalCheck]
    pass_count: int
    warn_count: int
    fail_count: int
    provider: dict
