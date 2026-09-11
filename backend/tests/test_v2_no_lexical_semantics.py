from __future__ import annotations

from pathlib import Path


V2_SEMANTIC_FILES = (
    "app/agents/v2/turn_contract.py",
    "app/agents/v2/semantic_context.py",
    "app/agents/v2/turn_interpreter.py",
)


def test_v2_semantic_runtime_has_no_regex_fuzzy_or_keyword_router() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = "\n".join(
        (backend / relative).read_text(encoding="utf-8")
        for relative in V2_SEMANTIC_FILES
    ).lower()

    forbidden = (
        "re.compile",
        "re.search",
        "re.match",
        "difflib.",
        "fuzzywuzzy",
        "rapidfuzz",
        'if "حجز" in',
        "if 'حجز' in",
        'if "الغاء" in',
        "if 'الغاء' in",
        'if "إلغاء" in',
        "if 'إلغاء' in",
    )
    for token in forbidden:
        assert token not in source


def test_v2_contract_does_not_reintroduce_legacy_semantic_outputs() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/v2/turn_contract.py").read_text(encoding="utf-8")
    forbidden_fields = (
        "SemanticCapability",
        "SemanticDomain",
        "FlowSignal",
        "recommended_handoff_category",
        "recommended_handoff_priority",
        "clear_entity_fields",
        "missing_information",
        "confidence",
        "reason:",
    )
    for token in forbidden_fields:
        assert token not in source
