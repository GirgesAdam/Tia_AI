from __future__ import annotations

import base64
import json
import os
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.clinic.base import AvailabilityRequest, ClinicCapability
from app.integrations.clinic.registry import get_clinic_adapter
from app.models.workspace import Workspace
from app.services.demo_reset import acquire_demo_request_lock
from tools.agent_eval import harness
from tools.agent_eval import run_batch_01 as batch

AFFECTED = [\n    batch.case_ambiguous_laser,\n    batch.case_package_other_service,\n    batch.case_multi_question,\n]\nGENERIC_SLUGS = {"hydrafacial"}
_fixture_context: dict = {}


def _bookable_context(db: Session, workspace: Workspace, *, service_slug: str | None = None, exclude_service_id: str | None = None):
    catalog = harness.build_clinic_catalog(db, workspace)
    branches = [r for r in catalog.get("branches", []) if isinstance(r, dict) and r.get("id")]
    if len(branches) != 1:
        raise RuntimeError(f"EVAL_INFRA_ERROR: active branches={len(branches)} expected=1")
    branch = branches[0]
    branch_id = str(branch["id"])
    services = [r for r in catalog.get("services", []) if isinstance(r, dict) and r.get("id")]
    doctors = [r for r in catalog.get("doctors", []) if isinstance(r, dict) and r.get("id")]
    exact_required = bool(service_slug and service_slug not in GENERIC_SLUGS)
    if service_slug and exact_required:
        required_id = db.execute(text("SELECT id FROM services WHERE workspace_id=:wid AND slug=:slug AND is_active IS TRUE"), {"wid": workspace.id, "slug": service_slug}).scalar_one_or_none()
        if required_id is None:
            raise RuntimeError(f"EVAL_INFRA_ERROR: required active service missing slug={service_slug!r}")
        services = [r for r in services if str(r.get("id")) == str(required_id)]
        if not services:
            raise RuntimeError(f"EVAL_INFRA_ERROR: required service absent from Agent active catalog slug={service_slug!r}")
    elif service_slug in GENERIC_SLUGS:
        preferred_raw = db.execute(text("SELECT id FROM services WHERE workspace_id=:wid AND slug=:slug AND is_active IS TRUE"), {"wid": workspace.id, "slug": service_slug}).scalar_one_or_none()
        preferred_id = str(preferred_raw) if preferred_raw is not None else None
        preferred = [r for r in services if str(r.get("id")) == preferred_id and not r.get("requires_laser_device")]
        fallback = [r for r in services if not r.get("requires_laser_device") and r not in preferred]
        services = preferred + fallback
