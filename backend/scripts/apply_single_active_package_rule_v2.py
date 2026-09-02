from __future__ import annotations

# Safely enforce one usable package per patient/service.
# Edits only backend/app/services/patient_packages.py and creates a backup.

from pathlib import Path
import shutil
import sys

SENTINEL = "Patient already has an active package for this service."


def _project_root() -> Path:
    here = Path.cwd().resolve()
    if (here / "app/services/patient_packages.py").exists():
        return here.parent
    if (here / "backend/app/services/patient_packages.py").exists():
        return here
    raise RuntimeError(
        "Could not find backend/app/services/patient_packages.py. "
        "Run this script from the repo root or backend/."
    )


def main() -> int:
    root = _project_root()
    target = root / "backend/app/services/patient_packages.py"
    backup = target.with_name("patient_packages.py.before_single_active_rule_v2")

    source = target.read_text(encoding="utf-8")
    start = source.find("def create_patient_package(")
    end = source.find("\ndef _package_financial_rows(", start)
    if start < 0 or end < 0:
        print(
            "Refusing to edit: create_patient_package() block was not found.",
            file=sys.stderr,
        )
        return 2

    block = source[start:end]
    if SENTINEL in block:
        print("Single-active-package rule is already applied. No changes made.")
        return 0

    old_patient = '''    patient = db.scalar(
        select(Patient).where(Patient.workspace_id == workspace_id, Patient.id == patient_id)
    )
'''
    new_patient = '''    patient = db.scalar(
        select(Patient)
        .where(Patient.workspace_id == workspace_id, Patient.id == patient_id)
        .with_for_update()
    )
'''
    if old_patient in block:
        block = block.replace(old_patient, new_patient, 1)
    elif ".with_for_update()" not in block:
        print(
            "Refusing to edit: expected patient lookup was not found.",
            file=sys.stderr,
        )
        return 3

    service_anchor = '''    if service is None or not service.is_active:
        raise PackageNotFound("Service not found or inactive.")
'''
    if service_anchor not in block:
        print(
            "Refusing to edit: service validation anchor was not found.",
            file=sys.stderr,
        )
        return 4

    rule = service_anchor + '''
    existing_usable = list_patient_packages(
        db,
        workspace_id=workspace_id,
        patient_id=patient_id,
        service_id=service_id,
        usable_only=True,
        on_date=purchased_at.date(),
    )
    if existing_usable:
        raise PackageOperationError(
            "Patient already has an active package for this service."
        )
'''
    block = block.replace(service_anchor, rule, 1)
    updated = source[:start] + block + source[end:]

    try:
        compile(updated, str(target), "exec")
    except SyntaxError as exc:
        print(f"Refusing to write invalid Python: {exc}", file=sys.stderr)
        return 5

    if not backup.exists():
        shutil.copy2(target, backup)

    target.write_text(updated, encoding="utf-8")
    print(f"Updated: {target}")
    print(f"Backup:  {backup}")
    print("Rule applied: one usable package per patient/service.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
