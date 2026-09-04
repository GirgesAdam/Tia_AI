import os
import subprocess
import sys


EXPECTED_HEAD = "0056_merge_automation_expenses"


def test_alembic_has_one_current_head() -> None:
    backend = os.path.dirname(os.path.dirname(__file__))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=backend,
        check=True,
        capture_output=True,
        text=True,
    )
    heads = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    assert heads == [f"{EXPECTED_HEAD} (head)"]
