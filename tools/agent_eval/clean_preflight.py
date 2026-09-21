from __future__ import annotations

import json
import unicodedata
from collections import Counter

from app.core.config import settings
from app.models.activity_event import ActivityEvent
from app.models.branch import Branch
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.demo_reset import (\n    DEMO_SEED_ACTION,\n    DEMO_SEED_VERSION,\n    RESET_RESEED_TABLES,\n    _table_rows,\n    _workspace_tables,\n)
from app.services.workspace_runtime_policy import workspace_runtime_policy
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(value.split())


def main() -> int:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(engine) as db:
        ws = db.scalar(select(Workspace).where(Workspace.slug == "tia"))
        if ws is None or not ws.is_demo or not ws.is_active:
            raise RuntimeError("EVAL_INFRA_ERROR: tia is not active Demo")
        policy = workspace_runtime_policy(ws)
        if any((policy.allow_external_dispatch, policy.allow_external_configuration, policy.allow_external_ingress, policy.allow_external_sync)):
            raise RuntimeError("EVAL_INFRA_ERROR: Demo external side effects are not blocked")

        seed_event = db.scalar(select(ActivityEvent).where(
            ActivityEvent.workspace_id == ws.id,
            ActivityEvent.action == DEMO_SEED_ACTION,
        ).order_by(ActivityEvent.created_at.desc()).limit(1))
        if seed_event is None:
            raise RuntimeError("EVAL_INFRA_ERROR: canonical seed missing")
        seed = dict(seed_event.metadata_json or {})
        if seed.get("seed_version") != DEMO_SEED_VERSION:
            raise RuntimeError(f"EVAL_INFRA_ERROR: unexpected seed {seed.get('seed_version')!r}")
        expected_services = int((seed.get("row_counts") or {}).get("services", -1))
        if expected_services < 0:
            raise RuntimeError("EVAL_INFRA_ERROR: seed service row count missing")

        seed_tables = seed.get("tables")
        if not isinstance(seed_tables, dict):
            raise RuntimeError("EVAL_INFRA_ERROR: canonical seed tables missing")
        workspace_tables = _workspace_tables()
        changed_tables = []
        for name in sorted(RESET_RESEED_TABLES):
            current_rows = _table_rows(db, workspace_tables[name], ws.id)
            if current_rows != seed_tables.get(name, []):
                changed_tables.append(name)
        if changed_tables:
            raise RuntimeError(
                "EVAL_INFRA_ERROR: Demo differs from canonical seed in "
                + ", ".join(changed_tables)
            )

        branches = list(db.scalars(select(Branch).where(
            Branch.workspace_id == ws.id,
            Branch.is_active.is_(True),
        ).order_by(Branch.name)))
        if len(branches) != 1:
            raise RuntimeError(f"EVAL_INFRA_ERROR: active branches={len(branches)} expected=1")

        services = list(db.scalars(select(Service).where(Service.workspace_id == ws.id).order_by(Service.name)))
        active = [s for s in services if s.is_active]
        inactive = [s for s in services if not s.is_active]
        if len(services) != expected_services:
            raise RuntimeError(f"EVAL_INFRA_ERROR: service rows={len(services)} seed={expected_services}")

        exact = sorted(k for k,v in Counter(s.name for s in active).items() if v > 1)
        normalized = sorted(k for k,v in Counter(norm(s.name) for s in active).items() if v > 1)
        fullbody = [s.name for s in active if norm(s.name) == "fullbody"]

        pricing = db.execute(text("""
            SELECT s.id, s.name, s.slug, s.requires_laser_device, s.price_minor,
                   COUNT(sdp.service_id) AS device_price_rows,
                   COUNT(sdp.service_id) FILTER (WHERE sdp.price_minor > 0) AS usable_device_prices
            FROM services s
            LEFT JOIN service_device_prices sdp
              ON sdp.workspace_id=s.workspace_id AND sdp.service_id=s.id
            WHERE s.workspace_id=:wid AND s.is_active IS TRUE
            GROUP BY s.id, s.name, s.slug, s.requires_laser_device, s.price_minor
            ORDER BY s.name
        """), {"wid": ws.id}).mappings().all()
        invalid_pricing = []
        for row in pricing:
            if row["requires_laser_device"]:
                if int(row["usable_device_prices"] or 0) <= 0:
                    invalid_pricing.append({"slug": row["slug"], "reason": "laser_requires_device_without_usable_device_price"})
            elif int(row["price_minor"] or 0) <= 0:
                invalid_pricing.append({"slug": row["slug"], "reason": "non_device_service_nonpositive_base_price"})

        required = {"hydrafacial", "prp-skin", "laser-hair-removal-full-body-women", "laser-hair-removal-underarm"}
        present = {s.slug for s in active}
        missing = sorted(required - present)

        catalog_inactive = db.execute(text("""
            SELECT COUNT(*) FROM services
            WHERE workspace_id=:wid AND is_active IS FALSE
        """), {"wid": ws.id}).scalar_one()

        report = {
            "canonical_preflight": "PASS",
            "canonical_reset": "NOT_NEEDED",
            "seed_version": DEMO_SEED_VERSION,
            "workspace_id": str(ws.id),
            "active_branch_count": len(branches),
            "branch_name": branches[0].name,
            "services_total": len(services),
            "services_expected_from_seed": expected_services,
            "services_active": len(active),
            "services_inactive": len(inactive),
            "exact_active_duplicates": exact,
            "normalized_active_duplicates": normalized,
            "unexpected_fullbody": fullbody,
            "invalid_pricing_rows": invalid_pricing,
            "missing_required_services": missing,
            "inactive_rows_present": int(catalog_inactive or 0),
        }
        print("CLEAN_PREFLIGHT=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)
        if exact or normalized or fullbody or invalid_pricing or missing:
            raise RuntimeError("EVAL_INFRA_ERROR: canonical service preflight failed")
    engine.dispose()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
