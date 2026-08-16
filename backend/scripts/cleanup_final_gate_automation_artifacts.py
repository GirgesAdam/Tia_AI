from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cleanup_test_automation_artifacts import main


if __name__ == "__main__":
    print(
        "[INFO] This command now cleans explicit Final Gate and "
        "staging-regression automation artifacts."
    )
    raise SystemExit(main())
