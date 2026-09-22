from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.v2.semantic_context import build_semantic_context
from app.core.config import settings
from app.models.workspace import Workspace
from tools.agent_eval.token_attribution import estimate_json_tokens


def compact_device_projection(
    services: list[dict[str, object]],
) -> dict[str, object]:
    devices: dict[str, str] = {}
    compact_services: list[dict[str, object]] = []

    for service in services:
        compact_service = {
            key: value
            for key, value in service.items()
            if key != "devices"
        }
        raw_devices = service.get("devices")
        if isinstance(raw_devices, list) and raw_devices:
            refs: list[str] = []
            for device in raw_devices:
                if not isinstance(device, dict):
                    continue
                ref = device.get("ref")
                name = device.get("name")
                if not isinstance(ref, str) or not ref:
                    continue
                refs.append(ref)
                if isinstance(name, str) and name:
                    devices.setdefault(ref, name)
            if refs:
                compact_service["device_refs"] = refs
        compact_services.append(compact_service)

    return {
        "services": compact_services,
        "devices": [
            {"ref": ref, "name": name}
            for ref, name in devices.items()
        ],
    }


def main() -> int:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    db = Session(engine)
    try:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if workspace is None:
            raise RuntimeError("Demo workspace not found.")
        model_input = build_semantic_context(
            build_clinic_catalog(db, workspace)
        ).model_input
        services = model_input.get("services")
        if not isinstance(services, list):
            raise RuntimeError("Semantic services missing.")
        typed_services = [
            row for row in services if isinstance(row, dict)
        ]
        projection = compact_device_projection(typed_services)
        print(
            "DEVICE_DEDUP_TOKENS="
            + json.dumps(
                {
                    "services_current": estimate_json_tokens(typed_services),
                    "projection_total": estimate_json_tokens(projection),
                    "services_compact": estimate_json_tokens(
                        projection["services"]
                    ),
                    "unique_devices": estimate_json_tokens(
                        projection["devices"]
                    ),
                    "device_count": len(projection["devices"]),
                    "laser_service_count": sum(
                        bool(row.get("devices"))
                        for row in typed_services
                    ),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    finally:
        db.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
