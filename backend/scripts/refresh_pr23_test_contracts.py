from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "backend" / "tests"


def replace(path: Path, old: str, new: str) -> bool:
    source = path.read_text(encoding="utf-8")
    if old not in source:
        return False
    path.write_text(source.replace(old, new), encoding="utf-8")
    return True


def main() -> None:
    changed: list[Path] = []

    # Historical phase tests used to hard-code 0060 as the current Alembic head.
    # Keep migration-specific revision assertions intact; only refresh readiness-head contracts.
    for path in TESTS.glob("test_*.py"):
        before = path.read_text(encoding="utf-8")
        after = before.replace(
            'assert EXPECTED_MIGRATION_HEAD == "0060_whatsapp_direct_credentials"',
            'assert EXPECTED_MIGRATION_HEAD == "0062_laser_device_scheduling"',
        ).replace(
            'assert \'EXPECTED_MIGRATION_HEAD = "0060_whatsapp_direct_credentials"\' in readiness',
            'assert \'EXPECTED_MIGRATION_HEAD = "0062_laser_device_scheduling"\' in readiness',
        ).replace(
            'assert \'EXPECTED_MIGRATION_HEAD = "0060_whatsapp_direct_credentials"\' in operational_readiness',
            'assert \'EXPECTED_MIGRATION_HEAD = "0062_laser_device_scheduling"\' in operational_readiness',
        )
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed.append(path)

    targeted_replacements = {
        TESTS / "test_booking_flow_relaxation.py": [
            ('assert "اختار الميعاد" in reply', 'assert "اختار الوقت" in reply'),
        ],
        TESTS / "test_busy_appointment_availability.py": [
            (
                'overlap_filter = source.index("not _overlaps_existing(", active_query)',
                'overlap_filter = source.index("doctor_busy = _overlaps_existing(", active_query)',
            ),
        ],
        TESTS / "test_customer_email_retirement_hotfix.py": [
            (
                '    assert set(long_revisions) == {"0052_payment_reference_constraint_repair"}\n',
                '    assert set(long_revisions) == {\n'
                '        "0052_payment_reference_constraint_repair",\n'
                '        "0061_clinic_ops_inventory_products",\n'
                '    }\n',
            ),
            (
                '    assert revisions["0034_drop_customer_email"] == "0033_sync_authority"\n',
                '    assert revisions["0034_drop_customer_email"] == "0033_sync_authority"\n'
                '    assert revisions["0061_clinic_ops_inventory_products"] == "0060_whatsapp_direct_credentials"\n',
            ),
        ],
        TESTS / "test_external_appointment_sync_phase62e.py": [
            (
                '            currency VARCHAR(3), requires_medical_review BOOLEAN, is_active BOOLEAN,',
                '            currency VARCHAR(3), requires_medical_review BOOLEAN, requires_laser_device BOOLEAN DEFAULT 0, is_active BOOLEAN,',
            ),
            (
                '            duration_minutes INTEGER, price_minor INTEGER, currency VARCHAR(3), payment_status VARCHAR(16),',
                '            duration_minutes INTEGER, price_minor INTEGER, currency VARCHAR(3), laser_device_key VARCHAR(40), laser_device_name VARCHAR(120), payment_status VARCHAR(16),',
            ),
        ],
        TESTS / "test_external_sync_engine_phase62c.py": [
            (
                '            price_minor INTEGER, currency VARCHAR(3), payment_status VARCHAR(16),',
                '            price_minor INTEGER, currency VARCHAR(3), laser_device_key VARCHAR(40), laser_device_name VARCHAR(120), payment_status VARCHAR(16),',
            ),
        ],
        TESTS / "test_historical_data_ai_retrieval_phase66.py": [
            (
                '            price_minor INTEGER, currency VARCHAR(3), payment_status VARCHAR(16),',
                '            price_minor INTEGER, currency VARCHAR(3), laser_device_key VARCHAR(40), laser_device_name VARCHAR(120), payment_status VARCHAR(16),',
            ),
            (
                '            reference_transaction_id CHAR(32), transaction_type VARCHAR(16), amount_minor INTEGER,',
                '            reference_transaction_id CHAR(32), patient_package_id CHAR(32), transaction_type VARCHAR(16), amount_minor INTEGER,',
            ),
        ],
        TESTS / "test_staff_analytics_bi_phase67.py": [
            (
                "            currency VARCHAR(3) DEFAULT 'EGP', requires_medical_review BOOLEAN DEFAULT 0,\n            is_active BOOLEAN DEFAULT 1,",
                "            currency VARCHAR(3) DEFAULT 'EGP', requires_medical_review BOOLEAN DEFAULT 0,\n            requires_laser_device BOOLEAN DEFAULT 0, is_active BOOLEAN DEFAULT 1,",
            ),
            (
                '            price_minor INTEGER, currency VARCHAR(3), payment_status VARCHAR(16),',
                '            price_minor INTEGER, currency VARCHAR(3), laser_device_key VARCHAR(40), laser_device_name VARCHAR(120), payment_status VARCHAR(16),',
            ),
            (
                '            reference_transaction_id CHAR(32), transaction_type VARCHAR(16), amount_minor INTEGER,',
                '            reference_transaction_id CHAR(32), patient_package_id CHAR(32), transaction_type VARCHAR(16), amount_minor INTEGER,',
            ),
        ],
        TESTS / "test_laser_device_resource_booking.py": [
            (
                '    db = _FakeDb(\n        assignments=[(doctor_branch, doctor_service, doctor)],\n        scalar_batches=[\n            branch_hours,\n            list(doctor_existing or []),',
                '    doctor_existing_rows = list(doctor_existing or [])\n'
                '    for appointment in doctor_existing_rows:\n'
                '        if not hasattr(appointment, "doctor_id"):\n'
                '            appointment.doctor_id = doctor_id\n\n'
                '    db = _FakeDb(\n'
                '        assignments=[(doctor_branch, doctor_service, doctor)],\n'
                '        scalar_batches=[\n'
                '            branch_hours,\n'
                '            doctor_existing_rows,',
            ),
            ('assert \'"excl_appointments_laser_device_busy_time"\' in migration', 'assert "excl_appointments_laser_device_busy_time" in migration'),
            ('assert \'("laser_device_key", "=")\' in migration', 'assert "laser_device_key WITH =" in migration'),
        ],
        TESTS / "test_payment_ledger_phase57.py": [
            (
                '    assert "Amount, type, origin_appointment_id and timestamps remain immutable" in payments',
                '    assert ".values(origin_appointment_id=to_appointment_id)" not in payments',
            ),
            (
                '    assert "If any ledger rows already exist, their derived snapshot wins" in payments',
                '    assert "if rows:" in payments\n'
                '    assert "sync_appointment_payment_snapshot(appointment, list(rows))" in payments',
            ),
        ],
    }

    for path, replacements in targeted_replacements.items():
        before = path.read_text(encoding="utf-8")
        after = before
        for old, new in replacements:
            after = after.replace(old, new)
        if after != before:
            path.write_text(after, encoding="utf-8")
            if path not in changed:
                changed.append(path)

    if changed:
        print("Refreshed test contracts:")
        for path in sorted(changed):
            print(f"- {path.relative_to(ROOT)}")
    else:
        print("Test contracts already current.")


if __name__ == "__main__":
    main()
