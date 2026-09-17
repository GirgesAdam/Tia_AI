from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import SessionLocal  # noqa: E402
from app.services.demo_reset import DemoResetError, capture_demo_canonical_seed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the approved canonical dataset for one demo workspace.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.confirm != "CAPTURE":
        print("REFUSED: --confirm CAPTURE is required.")
        return 2
    try:
        workspace_id = UUID(args.workspace_id)
    except ValueError:
        print("ERROR: invalid workspace UUID.")
        return 2
    try:
        with SessionLocal() as db:
            event = capture_demo_canonical_seed(
                db,
                workspace_id=workspace_id,
                replace=args.replace,
            )
    except DemoResetError as exc:
        print(f"ERROR: {exc}")
        return 3
    counts = (event.metadata_json or {}).get("row_counts", {})
    print(f"Canonical demo seed captured workspace={workspace_id} tables={len(counts)} rows={sum(counts.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
