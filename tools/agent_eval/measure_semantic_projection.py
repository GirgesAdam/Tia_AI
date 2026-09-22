from __future__ import annotations

import json

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.semantic_state_view import (
    with_safe_read_context,
    with_safe_task_context,
)
from app.core.config import settings
from app.models.workspace import Workspace
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tools.agent_eval.token_attribution import estimate_json_tokens


def _section_tokens(model_input: dict[str, object]) -> dict[str, int]:
    return {
        key: estimate_json_tokens(value)
        for key, value in model_input.items()
    }


def _first_laser_service(catalog: dict[str, object]) -> dict[str, object] | None:
    services = catalog.get("services")
    if not isinstance(services, list):
        return None
    for row in services:
        if isinstance(row, dict) and row.get("laser_devices"):
            return row
    return None


def main() -> int:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
            if workspace is None:
                raise RuntimeError("Demo workspace not found.")
            catalog = build_clinic_catalog(db, workspace)
            base = build_semantic_context(catalog)

            pricing = base
            booking = base
            laser = _first_laser_service(catalog)
            if laser is not None:
                devices = laser.get("laser_devices")
                device_key = None
                if isinstance(devices, list) and devices and isinstance(devices[-1], dict):
                    device_key = devices[-1].get("device_key")
                read_context: dict[str, object] = {
                    "operation_type": "pricing",
                    "service_id": laser.get("id"),
                }
                if device_key not in (None, ""):
                    read_context["device_key"] = device_key
                pricing = with_safe_read_context(base, read_context=read_context)

                constraints: dict[str, object] = {"service_id": laser.get("id")}
                doctor_ids = laser.get("doctor_ids")
                if isinstance(doctor_ids, list) and doctor_ids:
                    constraints["doctor_id"] = doctor_ids[0]
                booking = with_safe_task_context(
                    base,
                    active_task={
                        "task_type": "booking",
                        "status": "collecting",
                        "constraints": constraints,
                    },
                )

        payload = {
            "broad_total": estimate_json_tokens(base.model_input),
            "broad_sections": _section_tokens(base.model_input),
            "focused_pricing_total": estimate_json_tokens(pricing.model_input),
            "focused_pricing_sections": _section_tokens(pricing.model_input),
            "focused_booking_total": estimate_json_tokens(booking.model_input),
            "focused_booking_sections": _section_tokens(booking.model_input),
        }
        print(
            "SEMANTIC_PROJECTION_TOKENS="
            + json.dumps(payload, sort_keys=True),
            flush=True,
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
