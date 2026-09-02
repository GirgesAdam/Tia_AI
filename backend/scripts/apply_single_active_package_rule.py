from __future__ import annotations

"""Safely enforce one usable package per patient/service.

Edits only backend/app/services/patient_packages.py and creates a backup.
The change is intentionally narrow:
- serialize package creation per patient with SELECT ... FOR UPDATE;
- reject a new same-service package while another usable package remains.
- exhausted/cancelled/expired packages do not block a new purchase.

Run from the repo root or backend/.
"""

from pathlib import Path
import re
import shutil
import sys


def _project_root() -> Path:
    here = Path.cwd().resolve()
    if (here / "app/services/patient_packages.py").exists():
        return here.parent
    if (here / "backend/app/services/patient_packages.py").exists():
        return here
    raise RuntimeError(
        "Could not find backend/app/services/patient_packages.py. "
        "Run from the project root or backend/."
    )


def main() -> int:
    root = _project_root()
    target = root / "backend/app/services/patient_packages.py"
    backup = target.with_name("patient_packages.py.before_single_active_rule")
    source = target.read_text(encoding="utf-8")

    sentinel = "Patient already has an active package for this service."
    if sentinel in source:
        print("Single-active-package rule is already applied. No changes made.")
        return 0

    start = source.find("def create_patient_package(")
    end = source.find("\ndef _package_financial_rows(", start)
    if start < 0 or end < 0:
        print("Refusing to edit: create_patient_package() block was not found.", file=sys.stderr)
        return 2

    block = source[start:end]

    # Lock the patient row so two concurrent package purchases for the same
    # patient cannot both pass the active-package check.
    patient_pattern = re.compile(
        r"patient = db\.scalar\(\s*"
        r"select\(Patient\)\.where\(Patient\.workspace_id == workspace_id, Patient\.id == patient_id\)\s*"
        r"\)",
        re.MULTILINE,
    )
    patient_replacement = (
        "patient = db.scalar(\n"
        "        select(Patient)\n"
        "        .where(Patient.workspace_id == workspace_id, Patient.id == patient_id)\n"
        "        .with_for_update()\n"
        "    )"
    )
    block2, count = patient_pattern.subn(patient_replacement, block, count=1)
    if count != 1:
        print("Refusing to edit: expected patient lookup shape was not found.", file=sys.stderr)
        return 3

    needle = (
        '    if service is None or not service.is_active:\n'
        '        raise PackageNotFound("Service not found or inactive.")\n'
    )
    if needle not in block2:
        print("Refusing to edit: service validation anchor was not found.", file=sys.stderr)
        return 4

    insertion = needle + (
        "\n"
        "    existing_usable = list_patient_packages(\n"
        "        db,\n"
        "        workspace_id=workspace_id,\n"
        "        patient_id=patient_id,\n"
        "        service_id=service_id,\n"
        "        usable_only=True,\n"
        "        on_date=purchased_at.date(),\n"
        "    )\n"
        "    if existing_usable:\n"
        "        raise PackageOperationError(\n"
        '            "Patient already has an active package for this service."\n'
        "        )\n"
    )
    block2 = block2.replace(needle, insertion, 1)

    updated = source[:start] + block2 + source[end:]
    if not backup.exists():
        shutil.copy2(target, backup)
    target.write_text(updated, encoding="utf-8")

    print(f"Updated: {target}")
    print(f"Backup:  {backup}")
    print("Rule: one usable package per patient/service; exhausted packages allow a new purchase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
