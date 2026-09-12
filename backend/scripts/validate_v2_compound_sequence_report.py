from __future__ import annotations

import argparse
import json
from pathlib import Path

_EXPECTED_APPOINTMENTS = {
    "two_services_same_anchor_implicit": 2,
    "two_services_same_anchor_after_wording": 2,
    "same_visit_natural_phrase": 2,
    "book_then_buy_same_service_dependency": 1,
    "service_then_other_package_same_anchor": 2,
    "package_then_other_service_same_anchor": 2,
    "second_compound_slot_occupied_shift_next": 0,
}
_PACKAGE_CASES = {
    "book_then_buy_same_service_dependency",
    "service_then_other_package_same_anchor",
    "package_then_other_service_same_anchor",
}
_PACKAGE_USAGE_CASES = {
    "service_then_other_package_same_anchor",
    "package_then_other_service_same_anchor",
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="artifacts/v2-compound-sequence-review.json")
    return parser.parse_args()


def _checks(row: dict[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    raw = row.get("db_checks")
    if not isinstance(raw, list):
        return values
    for item in raw:
        if not isinstance(item, str) or "=" not in item:
            continue
        key, value = item.split("=", 1)
        values[key] = value
    return values


def _integer(values: dict[str, str], key: str) -> int | None:
    raw = values.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def validate_report(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return ["compound report root must be a list"]

    by_name = {
        str(row.get("name")): row
        for row in payload
        if isinstance(row, dict) and row.get("name")
    }
    errors: list[str] = []
    for name, expected_count in _EXPECTED_APPOINTMENTS.items():
        row = by_name.get(name)
        if row is None:
            errors.append(f"{name}: missing result")
            continue
        if row.get("error") not in (None, ""):
            errors.append(f"{name}: runtime error: {row.get('error')}")
            continue

        checks = _checks(row)
        actual_count = _integer(checks, "appointment_count")
        if actual_count != expected_count:
            errors.append(
                f"{name}: appointment_count expected {expected_count}, got {actual_count}"
            )

        if name in _PACKAGE_CASES:
            package_count = _integer(checks, "package_count")
            if package_count != 1:
                errors.append(f"{name}: package_count expected 1, got {package_count}")

        if name == "book_then_buy_same_service_dependency":
            if checks.get("appointment_package_id") in (None, "None"):
                errors.append(f"{name}: booked appointment is not linked to the purchased package")
            if checks.get("usage_status") != "reserved":
                errors.append(
                    f"{name}: expected reserved package usage, got {checks.get('usage_status')}"
                )

        if name in _PACKAGE_USAGE_CASES and checks.get("usage_links") in (None, "[]"):
            errors.append(f"{name}: expected one booked session linked to the purchased package")

    return errors


def main() -> int:
    path = Path(_args().report)
    errors = validate_report(path)
    if errors:
        print("Compound review DB invariant failures:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Compound review DB invariants verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
