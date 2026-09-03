from __future__ import annotations

import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_realistic_aesthetic_clinic.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _literal(name: str):
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"Missing literal {name}")


def test_fixture_is_non_production_only() -> None:
    assert "Refusing to seed synthetic clinic data into ENVIRONMENT=production" in SOURCE
    assert "settings.is_production" in SOURCE


def test_fixture_has_realistic_branch_coverage() -> None:
    branches = _literal("BRANCHES")
    assert len(branches) >= 3
    assert {row["code"] for row in branches} >= {"nasr-city", "new-cairo", "sheikh-zayed"}


def test_fixture_has_broad_service_catalog() -> None:
    services = _literal("SERVICES")
    assert len(services) >= 25
    names = {row["name"] for row in services}
    assert "ليزر إزالة الشعر" in names
    assert "فراكشنال CO2 لآثار حب الشباب" in names
    assert "إزالة الوشم بالليزر" in names
    assert "هيدرافيشل" in names
    assert "بوتوكس" in names
    assert "PRP للشعر" in names
    assert any(row["medical"] for row in services)
    assert any(not row["medical"] for row in services)


def test_fixture_has_doctor_branch_and_schedule_edge_cases() -> None:
    # DOCTORS references HAIR_LASER_KEYS, so validate the source contract rather than literal_eval.
    assert '"branches": ["nasr-city"]' in SOURCE
    assert '"branches": ["new-cairo"]' in SOURCE
    assert '"branches": ["nasr-city", "new-cairo"]' in SOURCE
    assert '"branches": ["new-cairo", "sheikh-zayed"]' in SOURCE
    assert '("16:00", "19:00"), ("20:00", "22:00")' in SOURCE
    assert '"custom_services"' in SOURCE


def test_fixture_deactivates_legacy_demo_and_regression_records_by_default() -> None:
    assert 'code.startswith("demo-")' in SOURCE
    assert 'code.startswith("regression-")' in SOURCE
    assert 'slug.startswith("demo-")' in SOURCE
    assert 'slug.startswith("regression-")' in SOURCE


def test_fixture_seeds_availability_and_lifecycle_scenarios() -> None:
    expected = {
        "ahmed-tuesday-18-busy",
        "sara-wednesday-14-pending",
        "nour-thursday-17-botox",
        "ahmed-thursday-18-cancelled",
        "history-completed",
        "history-no-show",
        "multiple-upcoming-1",
        "multiple-upcoming-2",
    }
    for key in expected:
        assert key in SOURCE


def test_fixture_never_creates_external_messages() -> None:
    assert "Message(" not in SOURCE
    assert "MessageDispatch(" not in SOURCE
    assert "queue_patient" not in SOURCE
    assert '"external_messages_created": False' in SOURCE


def test_scenario_appointment_sources_match_database_constraint() -> None:
    # Appointment.source does not accept ``referral`` (Patient.source does).
    # Keep the synthetic scenario aligned with APPOINTMENT_SOURCES so the seed
    # cannot fail late on ck_appointments_appointment_source_valid.
    assert 'source="referral"' not in SOURCE[SOURCE.index("def create_scenario_appointments"): ]
    assert 'source="other"' in SOURCE[SOURCE.index("def create_scenario_appointments"): ]
    assert "APPOINTMENT_SOURCES" in SOURCE
    assert "APPOINTMENT_STATUSES" in SOURCE
    assert "if source not in APPOINTMENT_SOURCES" in SOURCE
    assert "if status not in APPOINTMENT_STATUSES" in SOURCE
