from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{path}: expected one occurrence of {old!r}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    ROOT / "backend/app/services/operational_readiness.py",
    'EXPECTED_MIGRATION_HEAD = "0055_lead_followup"',
    'EXPECTED_MIGRATION_HEAD = "0056_merge_automation_expenses"',
)
replace_once(
    ROOT / "backend/tests/test_automation_operations_phase54.py",
    'EXPECTED_MIGRATION_HEAD = "0055_lead_followup"',
    'EXPECTED_MIGRATION_HEAD = "0056_merge_automation_expenses"',
)

print("current migration head aligned")
