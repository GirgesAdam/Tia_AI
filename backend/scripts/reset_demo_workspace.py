from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import SessionLocal  # noqa: E402
from app.services.demo_reset import DemoResetError, reset_demo_workspace  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore one demo workspace to its canonical dataset.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.confirm != "RESET":
        print("REFUSED: --confirm RESET is required.")
        return 2
    try:
        workspace_id = UUID(args.workspace_id)
    except ValueError:
        print("ERROR: invalid workspace UUID.")
        return 2
    try:
        with SessionLocal() as db:
            result = reset_demo_workspace(db, workspace_id=workspace_id)
    except DemoResetError as exc:
        print(f"ERROR: {exc}")
        return 3
    print(
        "Demo reset complete "
        f"workspace={result.workspace_id} seed={result.seed_version} "
        f"date={result.reset_date} reseeded={result.reseeded_rows} cleared={result.cleared_rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
