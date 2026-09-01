from pathlib import Path


def test_semantic_output_uses_native_json_schema_only() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/agents/structured_output.py").read_text(encoding="utf-8")

    assert 'method="json_schema"' in source
    assert "json_object" not in source
    assert "function_calling" not in source
    assert "Retry-After" not in source
