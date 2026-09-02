from pathlib import Path


def test_semantic_matrix_covers_package_session_intent_contract() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8")

    required_cases = (
        "package_purchase_explicit",
        "package_purchase_multisession_plan",
        "package_inquiry_compare",
        "package_use_existing",
        "package_avoid_existing",
        "single_session_no_package_intent",
    )
    for case in required_cases:
        assert case in source

    for intent in ("purchase", "inquire", "use_existing", "avoid_existing", "none"):
        assert f'_package_intent("{intent}")' in source


def test_package_semantic_matrix_does_not_use_runtime_lexical_routing() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_agent_e2e_matrix.py").read_text(encoding="utf-8").lower()

    assert "re.compile" not in source
    assert "re.search" not in source
    assert "re.match" not in source
