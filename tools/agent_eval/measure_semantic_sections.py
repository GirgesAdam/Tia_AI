from __future__ import annotations

import json

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.v2.semantic_context import build_semantic_context
from app.core.config import settings
from app.models.workspace import Workspace
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tools.agent_eval.token_attribution import estimate_json_tokens


def main() -> int:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
            if workspace is None:
                raise RuntimeError("Demo workspace not found.")
            model_input = build_semantic_context(
                build_clinic_catalog(db, workspace)
            ).model_input

        sections = {
            key: {
                "tokens": estimate_json_tokens(value),
                "count": len(value) if isinstance(value, list) else None,
            }
            for key, value in model_input.items()
        }
        services = list(model_input.get("services") or [])
        doctors = list(model_input.get("doctors") or [])
        service_names_only = [
            {key: row[key] for key in ("ref", "name") if key in row}
            for row in services
            if isinstance(row, dict)
        ]
        services_without_category = [
            {
                key: row[key]
                for key in ("ref", "name", "requires_laser_device", "devices")
                if key in row
            }
            for row in services
            if isinstance(row, dict)
        ]
        services_without_laser_flag = [
            {key: row[key] for key in ("ref", "name", "category", "devices") if key in row}
            for row in services
            if isinstance(row, dict)
        ]
        doctor_names_only = [
            {key: row[key] for key in ("ref", "name") if key in row}
            for row in doctors
            if isinstance(row, dict)
        ]
        print(
            "SEMANTIC_SECTION_TOKENS="
            + json.dumps(
                {
                    "sections": sections,
                    "projections": {
                        "services_full": estimate_json_tokens(services),
                        "services_identity_only": estimate_json_tokens(service_names_only),
                        "services_without_category": estimate_json_tokens(
                            services_without_category
                        ),
                        "services_without_laser_flag": estimate_json_tokens(
                            services_without_laser_flag
                        ),
                        "doctors_full": estimate_json_tokens(doctors),
                        "doctors_identity_only": estimate_json_tokens(doctor_names_only),
                        "devices_full": estimate_json_tokens(
                            list(model_input.get("devices") or [])
                        ),
                    },
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
