from pathlib import Path


def test_final_gate_fixture_source_uses_approved_synthetic_data() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts" / "seed_final_internal_gate.py").read_text(encoding="utf-8")

    for name in (
        "محمود",
        "سلمى",
        "ياسمين",
        "نورهان",
        "كريم",
        "هند",
        "ريم",
    ):
        assert name in source

    assert "+20109992" not in source
    assert "+20109993" not in source
    assert "+200000" in source
    assert "source_detail=GATE_MARKER" in source
    assert "FinalGate" not in source
    assert "RaceA" not in source
    assert "AutoMove" not in source


def test_full_staging_contacts_are_safe_reserved_test_contacts() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts" / "seed_full_staging_demo.py").read_text(encoding="utf-8")

    assert "+2010999" not in source
    assert "@tia.local" not in source
    assert "@staging-regression.tia.local" not in source
    assert "+200000" in source
    assert "@tia.example" in source  # branch/staff synthetic contacts
    assert "@staging-regression.tia.example" not in source  # patients are phone-only


def test_data_quality_validator_checks_runtime_rows() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts" / "validate_final_gate_fixture_quality.py").read_text(
        encoding="utf-8"
    )

    assert "settings.is_production" in source
    assert "patient.marketing_consent is False" in source
    assert "patient.source_detail == GATE_MARKER" in source
    assert "patient.email" not in source
    assert "secondary_appt.end_at > secondary_appt.start_at" in source


def test_full_final_gate_runs_fixture_quality_before_e2e() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts" / "run_final_internal_gate.py").read_text(encoding="utf-8")

    assert "validate_final_gate_fixture_quality.py" in source
    assert "Final Gate fixture data quality" in source
    assert source.index("validate_final_gate_fixture_quality.py") < source.index("7. FRONTEND E2E")
