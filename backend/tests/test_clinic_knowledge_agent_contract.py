from inspect import getsource
from pathlib import Path

from app.services import agent_chat


def test_curated_knowledge_is_prefetched_only_after_grounding() -> None:
    source = getsource(agent_chat._run_after_inbound)
    semantic_call = source.index("interpret_customer_turn(")
    knowledge_call = source.index("relevant_knowledge_context(")
    assert knowledge_call > semantic_call
    assert 'prefetched_results["clinic_knowledge"]' in source
    assert 'include_clinic=include_clinic_knowledge' in source


def test_knowledge_does_not_enter_semantic_catalog_builder() -> None:
    source = getsource(agent_chat._run_after_inbound)
    catalog_section = source[
        source.index("clinic_catalog = build_clinic_catalog") : source.index(
            "interpret_customer_turn("
        )
    ]
    assert "relevant_knowledge_context" not in catalog_section


def test_clinic_knowledge_table_is_not_exposed_through_supabase_data_api() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0066_clinic_knowledge_entries.py"
    ).read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL ON TABLE public.clinic_knowledge_entries FROM anon, authenticated" in migration
