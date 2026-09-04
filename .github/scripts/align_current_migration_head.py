from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD_HEAD = "0055_lead_followup"
NEW_HEAD = "0056_merge_automation_expenses"
MIGRATION_SPEC_TEST = "test_lead_followup_automation.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{path}: expected one occurrence of {old!r}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    ROOT / "backend/app/services/operational_readiness.py",
    f'EXPECTED_MIGRATION_HEAD = "{OLD_HEAD}"',
    f'EXPECTED_MIGRATION_HEAD = "{NEW_HEAD}"',
)

updated_tests = 0
for path in sorted((ROOT / "backend/tests").rglob("*.py")):
    if path.name == MIGRATION_SPEC_TEST:
        continue
    text = path.read_text(encoding="utf-8")
    if OLD_HEAD not in text:
        continue
    occurrences = text.count(OLD_HEAD)
    path.write_text(text.replace(OLD_HEAD, NEW_HEAD), encoding="utf-8")
    updated_tests += occurrences

if updated_tests != 18:
    raise AssertionError(f"expected 18 stale migration-head assertions, updated {updated_tests}")

print(f"current migration head aligned; updated {updated_tests} stale test assertions")
