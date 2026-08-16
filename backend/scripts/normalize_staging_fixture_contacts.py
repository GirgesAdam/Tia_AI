from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.branch import Branch
from app.models.patient import Patient
from app.models.staff import Staff
from staging_scenarios import sid


SEED_MARKER = "tia-full-staging-regression"

BRANCH_CONTACTS = {
    "branch:regression-main": (
        "+200000100001",
        "regression-main@tia.example",
    ),
    "branch:regression-secondary": (
        "+200000100002",
        "regression-new-cairo@tia.example",
    ),
}

STAFF_CONTACTS = {
    "staff:regression-doctor-main": (
        "+200000110001",
        "regression-doctor-1@tia.example",
    ),
    "staff:regression-doctor-second": (
        "+200000110002",
        "regression-doctor-2@tia.example",
    ),
}

PATIENT_KEYS = (
    "active",
    "inactive",
    "blocked",
    "lead_new",
    "lead_qualified",
    "lead_lost",
    "booking_pending",
    "booking_confirmed",
    "booking_policy_cancel",
    "booking_lifecycle",
    "booking_reschedule",
    "booking_idempotent",
    "automation_success",
    "automation_no_route",
    "handoff_medical",
    "handoff_complaint",
    "handoff_resolved",
    "channel",
    "agent_booking",
)


def normalize(workspace_id: UUID) -> dict[str, int]:
    """
    Normalize contact fields only.

    The script intentionally does not rename deterministic regression entities,
    replace IDs, or rebuild appointments/conversations. It is safe to run before
    focused E2E work and is idempotent.
    """
    if settings.is_production:
        raise RuntimeError("Staging fixture normalization refuses production.")

    changed = {"branches": 0, "staff": 0, "patients": 0}

    with SessionLocal() as db:
        for key, (phone, email) in BRANCH_CONTACTS.items():
            row = db.get(Branch, sid(workspace_id, key))
            if row is None:
                continue
            if row.phone != phone or row.email != email:
                row.phone = phone
                row.email = email
                changed["branches"] += 1

        for key, (phone, email) in STAFF_CONTACTS.items():
            row = db.get(Staff, sid(workspace_id, key))
            if row is None:
                continue
            if row.phone != phone or row.email != email:
                row.phone = phone
                row.email = email
                changed["staff"] += 1

        rows = list(
            db.scalars(
                select(Patient).where(
                    Patient.workspace_id == workspace_id,
                    Patient.source_detail == SEED_MARKER,
                )
            )
        )
        by_id = {row.id: row for row in rows}
        for index, key in enumerate(PATIENT_KEYS, start=1):
            row = by_id.get(sid(workspace_id, f"patient:{key}"))
            if row is None:
                continue
            phone = f"+20000012{index:04d}"
            email = f"{key}@staging-regression.tia.example"
            if (
                row.phone != phone
                or row.phone_normalized != phone
                or row.email != email
            ):
                row.phone = phone
                row.phone_normalized = phone
                row.email = email
                changed["patients"] += 1

        db.commit()

    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    try:
        result = normalize(UUID(args.workspace_id))
    except Exception as exc:
        print(
            "[FAIL] Staging fixture contact normalization — "
            f"{type(exc).__name__}: {exc}"
        )
        return 2

    print(
        "[PASS] Staging fixture contacts normalized "
        f"(branches={result['branches']}, "
        f"staff={result['staff']}, patients={result['patients']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
