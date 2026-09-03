from __future__ import annotations

"""Run the live semantic regression matrix against the staging clinic catalog.

This is a staging-only harness. It resolves expected fixture IDs from canonical
PostgreSQL rows, then sends the original natural-language messages through the
real unified LLM turn interpreter. No lexical routing is implemented here.
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.clinic_grounding import build_clinic_catalog
from app.agents.turn_interpreter import interpret_customer_turn
from app.core.config import settings
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.service import Service
from app.models.staff import Staff
from app.models.workspace import Workspace
from scripts.run_agent_e2e_matrix import CheckResult, SuiteReport, _record, _semantic_cases


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Tia live semantic staging regression.")
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument(
        "--report",
        default="artifacts/live-semantic-staging.json",
        help="JSON report path, relative to backend unless absolute.",
    )
    return parser.parse_args()


def _catalog_ids(catalog: dict[str, object], collection: str) -> set[str]:
    rows = catalog.get(collection)
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("id"))
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def _fixture_expected(db: Session, workspace: Workspace, catalog: dict[str, object]) -> dict[str, object]:
    underarm = db.scalar(
        select(Service).where(
            Service.workspace_id == workspace.id,
            Service.slug == "laser-hair-removal-underarm",
            Service.is_active.is_(True),
        )
    )
    if underarm is None:
        raise RuntimeError("Canonical underarm staging service is missing or inactive.")

    nasr = db.scalar(
        select(Branch).where(
            Branch.workspace_id == workspace.id,
            Branch.name == "مدينة نصر",
            Branch.is_active.is_(True),
        )
    )
    if nasr is None:
        raise RuntimeError("Active Nasr City staging branch is missing.")

    ahmed = db.scalar(
        select(Doctor)
        .join(
            Staff,
            (Staff.workspace_id == Doctor.workspace_id) & (Staff.id == Doctor.staff_id),
        )
        .where(
            Doctor.workspace_id == workspace.id,
            Doctor.is_active.is_(True),
            Doctor.booking_enabled.is_(True),
            Staff.is_active.is_(True),
            Staff.first_name == "أحمد",
            Staff.last_name == "محمود",
        )
    )
    if ahmed is None:
        raise RuntimeError("Active Ahmed Mahmoud staging doctor is missing.")

    allowed_ids = {
        value
        for collection in ("services", "doctors", "branches")
        for value in _catalog_ids(catalog, collection)
    }
    required = {
        "underarm_service_id": str(underarm.id),
        "ahmed_doctor_id": str(ahmed.id),
        "nasr_branch_id": str(nasr.id),
    }
    missing = [value for value in required.values() if value not in allowed_ids]
    if missing:
        raise RuntimeError(f"Required canonical fixture IDs are absent from the agent catalog: {missing}")

    return {**required, "allowed_ids": allowed_ids}


def main() -> int:
    args = _parse_args()
    environment = str(settings.environment or "").strip().lower()
    if environment != "staging":
        print("Refusing to run live semantic staging regression outside staging.", file=sys.stderr)
        return 2

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    report: SuiteReport | None = None
    try:
        with Session(engine, expire_on_commit=False) as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == args.workspace_slug))
            if workspace is None:
                raise RuntimeError("Workspace not found.")

            report = SuiteReport(
                started_at=datetime.now(ZoneInfo("UTC")).isoformat(),
                workspace_id=str(workspace.id),
                workspace_slug=workspace.slug,
                profile="semantic",
                rollback=True,
            )

            started = perf_counter()
            catalog = build_clinic_catalog(db, workspace)
            catalog_ok = bool(catalog.get("services") and catalog.get("branches") and catalog.get("doctors"))
            _record(
                report,
                CheckResult(
                    name="active_catalog",
                    category="setup",
                    status="PASS" if catalog_ok else "FAIL",
                    duration_ms=int((perf_counter() - started) * 1000),
                    details={
                        "services": len(catalog.get("services", [])),
                        "branches": len(catalog.get("branches", [])),
                        "doctors": len(catalog.get("doctors", [])),
                    },
                    error=None if catalog_ok else "Active staging catalog is incomplete.",
                ),
            )
            if not catalog_ok:
                raise RuntimeError("Active staging catalog is incomplete.")

            expected = _fixture_expected(db, workspace, catalog)
            timezone_name = (workspace.timezone or "Africa/Cairo").strip()
            local_now = datetime.now(ZoneInfo(timezone_name))

            for case in _semantic_cases():
                started = perf_counter()
                try:
                    decision = interpret_customer_turn(
                        flow=None,
                        history=[HumanMessage(content=case.message)],
                        timezone_name=timezone_name,
                        local_now=local_now,
                        clinic_catalog=catalog,
                    )
                    ok, message = case.check(decision, expected)
                    _record(
                        report,
                        CheckResult(
                            name=case.name,
                            category=f"semantic:{case.category}",
                            status="PASS" if ok else "FAIL",
                            duration_ms=int((perf_counter() - started) * 1000),
                            details={
                                "message": case.message,
                                "capabilities": list(decision.capabilities or []),
                                "flow_signal": str(decision.flow_signal),
                                "package_intent": str(getattr(decision, "package_intent", "none")),
                                "risk_flags": list(decision.risk_flags or []),
                                "entity_hints": decision.entity_hints.model_dump(mode="json"),
                                "confidence": decision.confidence,
                                "check": message,
                            },
                            error=None if ok else message,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001 - keep the matrix running
                    _record(
                        report,
                        CheckResult(
                            name=case.name,
                            category=f"semantic:{case.category}",
                            status="FAIL",
                            duration_ms=int((perf_counter() - started) * 1000),
                            details={"message": case.message},
                            error=f"{type(exc).__name__}: {exc}",
                        ),
                    )

            counts = report.counts()
            exit_code = 1 if counts.get("FAIL", 0) else 0
    except Exception as exc:  # noqa: BLE001 - report setup failures cleanly
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        if report is None:
            return 1
        _record(
            report,
            CheckResult(
                name="suite_exception",
                category="setup",
                status="FAIL",
                duration_ms=0,
                error=f"{type(exc).__name__}: {exc}",
            ),
        )
        exit_code = 1
    finally:
        engine.dispose()

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = Path.cwd() / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **{key: value for key, value in asdict(report).items() if key != "results"},
        "counts": report.counts(),
        "results": [asdict(row) for row in report.results],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSummary:", json.dumps(report.counts(), ensure_ascii=False))
    print(f"Report: {report_path}")
    print("Database writes performed: no")
    print("WhatsApp/n8n used: no")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
