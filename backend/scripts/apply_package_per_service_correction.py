from __future__ import annotations

from pathlib import Path
import shutil
import sys

BACKUP_SUFFIX = ".before_package_per_service_correction"


def _backend_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "app/services/agent_chat.py").exists():
        return cwd
    if (cwd / "backend/app/services/agent_chat.py").exists():
        return cwd / "backend"
    raise RuntimeError("Could not find backend/app/services/agent_chat.py")


def _patch_patient_packages(source: str) -> str:
    start = source.find("def create_patient_package(")
    if start < 0:
        raise RuntimeError("create_patient_package() not found")
    end = source.find("\ndef ", start + 1)
    if end < 0:
        end = len(source)

    block = source[start:end]

    if (
        "service_id=service_id" in block
        and "Patient already has an active package for this service." in block
    ):
        return source

    old1 = '''    existing_usable = list_patient_packages(
        db,
        workspace_id=workspace_id,
        patient_id=patient_id,
        service_id=None,
        usable_only=True,
        on_date=purchased_at.date(),
    )
    if existing_usable:
        raise PackageOperationError(
            "Patient already has an active package."
        )
'''
    new1 = '''    existing_usable = list_patient_packages(
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

    old2 = '''    existing_usable = list_patient_packages(
        db, workspace_id=workspace_id, patient_id=patient_id, service_id=None,
        usable_only=True, on_date=purchased_at.date(),
    )
    if existing_usable:
        raise PackageOperationError("Patient already has an active package.")
'''
    new2 = '''    existing_usable = list_patient_packages(
        db, workspace_id=workspace_id, patient_id=patient_id, service_id=service_id,
        usable_only=True, on_date=purchased_at.date(),
    )
    if existing_usable:
        raise PackageOperationError(
            "Patient already has an active package for this service."
        )
'''

    if old1 in block:
        block = block.replace(old1, new1, 1)
    elif old2 in block:
        block = block.replace(old2, new2, 1)
    else:
        raise RuntimeError(
            "Could not find the previously-applied global active-package rule."
        )

    return source[:start] + block + source[end:]


def _patch_agent_chat(source: str) -> str:
    global_lookup = 'service_id=("" if str(decision.package_intent) == "purchase" else service_id),'
    if global_lookup in source:
        source = source.replace(global_lookup, "service_id=service_id,", 1)

    old_reply = (
        'return f"عندك {name} شغالة حالياً وفاضلك {remaining} جلسات. '
        'لازم تخلص الباكدج الحالية الأول قبل بدء باكدج جديدة."'
    )
    new_reply = (
        'return f"عندك {name} لنفس الخدمة شغالة حالياً وفاضلك {remaining} جلسات. '
        'استخدم الجلسات المتبقية فيها الأول قبل بدء باكدج جديدة لنفس الخدمة."'
    )
    if old_reply in source:
        source = source.replace(old_reply, new_reply, 1)

    return source


def _patch_semantic_prompt(source: str) -> str:
    variants = [
        (
            '"a normal paid appointment instead of using an existing package. A purchase request is NOT a "',
            '"a normal paid appointment instead of using an existing package. '
            'An existing package for one service does not block or change a request to purchase a package '
            'for a different service. Classify the requested new package from its own service and the latest '
            'customer intent. A purchase request is NOT a "',
        ),
        (
            '"outside the package. If the customer corrects an active booking into a package purchase, that "',
            '"outside the package. An existing package for one service does not block or change a package '
            'purchase for a different service. Classify that new package as purchase when the customer wants '
            'to obtain/start it. If the customer corrects an active booking into a package purchase, that "',
        ),
        (
            '"avoid_existing when they explicitly want a normal paid appointment instead of using the package. "',
            '"avoid_existing when they explicitly want a normal paid appointment instead of using the package. '
            'An existing package for one service does not block or change a request to purchase a package '
            'for a different service; classify the requested package independently from the old package. "',
        ),
    ]
    for old, new in variants:
        if new in source:
            return source
        if old in source:
            return source.replace(old, new, 1)
    return source


def main() -> int:
    backend = _backend_root()

    patches = {
        backend / "app/services/patient_packages.py": _patch_patient_packages,
        backend / "app/services/agent_chat.py": _patch_agent_chat,
        backend / "app/agents/semantic_router.py": _patch_semantic_prompt,
        backend / "app/agents/flow_interpreter.py": _patch_semantic_prompt,
        backend / "app/agents/turn_interpreter.py": _patch_semantic_prompt,
    }

    prepared: dict[Path, str] = {}
    try:
        for path, patcher in patches.items():
            original = path.read_text(encoding="utf-8")
            updated = patcher(original)
            compile(updated, str(path), "exec")
            prepared[path] = updated
    except Exception as exc:
        print(
            f"No files were changed. Correction failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    for path, updated in prepared.items():
        original = path.read_text(encoding="utf-8")
        if original == updated:
            print(f"Already correct / unchanged: {path}")
            continue

        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(path, backup)

        path.write_text(updated, encoding="utf-8")
        print(f"Updated: {path}")
        print(f"Backup:  {backup}")

    print()
    print("Applied correct package rule:")
    print("- different-service active packages may coexist")
    print("- same-service package purchase is blocked while the old package is usable")
    print("- no keyword/regex routing added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
