from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, or_

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.automation_job import AutomationJob


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Delete only explicitly marked Final Gate / staging-regression "
            "automation job artifacts in non-production environments."
        )
    )
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    if settings.is_production:
        print("Refusing test-artifact cleanup in production.", file=sys.stderr)
        return 2

    workspace_id = UUID(args.workspace_id)

    with SessionLocal() as db:
        result = db.execute(
            delete(AutomationJob).where(
                AutomationJob.workspace_id == workspace_id,
                or_(
                    AutomationJob.dedupe_key.like("final-gate-%"),
                    AutomationJob.dedupe_key.like("staging-regression:%"),
                    AutomationJob.payload_json["marker"].astext.in_(
                        (
                            "final-gate",
                            "final-gate-stale",
                            "staging-regression",
                            "tia-full-staging-regression",
                        )
                    ),
                ),
            )
        )
        db.commit()
        deleted = int(result.rowcount or 0)

    print(
        "[PASS] Deleted "
        f"{deleted} explicit automation test artifact job(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
