from pathlib import Path


def test_normalizer_is_contact_only_and_staging_guarded() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "scripts" / "normalize_staging_fixture_contacts.py"
    ).read_text(encoding="utf-8")

    assert "settings.is_production" in source
    assert "+200000" in source
    assert ".example" in source
    assert "row.phone =" in source
    assert "row.email =" in source

    forbidden_business_mutations = (
        "Appointment(",
        "Conversation(",
        "delete(Appointment",
        "delete(Conversation",
        "row.name =",
        "row.first_name =",
        "row.last_name =",
    )
    for token in forbidden_business_mutations:
        assert token not in source


def test_focused_gate_normalizes_legacy_contacts_before_quality_validation() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "scripts" / "run_frontend_e2e_gate.py"
    ).read_text(encoding="utf-8")

    normalizer = "normalize_staging_fixture_contacts.py"
    validator = "validate_final_gate_fixture_quality.py"
    assert normalizer in source
    assert validator in source
    assert source.index(normalizer) < source.index(validator)


def test_fixture_policy_prefers_realistic_final_gate_for_new_product_tests() -> None:
    backend = Path(__file__).resolve().parent.parent
    policy = (backend / "FIXTURE_DATA_POLICY.md").read_text(encoding="utf-8")

    assert "Realistic E2E / Agent fixtures" in policy
    assert "Technical regression fixtures" in policy
    assert "New product-level tests should prefer" in policy
