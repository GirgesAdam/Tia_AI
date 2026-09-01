from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_payments_module_imports_in_clean_python_process() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import app.services.payments"],
        cwd=_backend_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_package_level_adapter_export_remains_compatible_without_eager_cycle() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.integrations.clinic import TiaDatabaseClinicAdapter; "
            "assert TiaDatabaseClinicAdapter.__name__ == 'TiaDatabaseClinicAdapter'",
        ],
        cwd=_backend_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
