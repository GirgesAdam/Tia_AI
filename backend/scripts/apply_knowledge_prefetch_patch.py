from pathlib import Path

path = Path("backend/app/services/agent_chat.py")
source = path.read_text(encoding="utf-8")

import_anchor = "from app.services.compound_customer_requests import (\n"
if "from app.services.clinic_knowledge_base import relevant_knowledge_context\n" not in source:
    source = source.replace(
        import_anchor,
        "from app.services.clinic_knowledge_base import relevant_knowledge_context\n" + import_anchor,
        1,
    )

anchor = '''            if catalog_facts is not None:\n                prefetched_results["clinic_catalog"] = catalog_facts\n                snapshot = choice_snapshot_from_grounded_facts(catalog_facts)\n'''
replacement = '''            if catalog_facts is not None:\n                prefetched_results["clinic_catalog"] = catalog_facts\n                snapshot = choice_snapshot_from_grounded_facts(catalog_facts)\n'''
if anchor not in source:
    raise SystemExit("catalog facts anchor not found")

# Curated knowledge is intentionally added only after the semantic interpreter has
# grounded canonical entities. It never goes into the interpreter catalog itself.
insert_anchor = '''        if (\n            grounded_mode\n            and "clinic_catalog" not in prefetched_results\n'''
knowledge_block = '''        if grounded_mode and not policy.requires_human:\n            service_uuid = _uuid_from_metadata(semantic_decision.entity_hints.service_id)\n            device_key = str(semantic_decision.entity_hints.laser_device_key or "").strip() or None\n            include_clinic_knowledge = "clinic_information" in set(policy.capabilities)\n            if (\n                include_clinic_knowledge\n                or service_uuid is not None\n                or device_key is not None\n            ) and set(policy.capabilities).intersection(\n                {"clinic_information", "service_information", "pricing"}\n            ):\n                knowledge_context = relevant_knowledge_context(\n                    db,\n                    workspace_id=workspace.id,\n                    service_id=service_uuid,\n                    device_key=device_key,\n                    include_clinic=include_clinic_knowledge,\n                )\n                if knowledge_context is not None:\n                    prefetched_results["clinic_knowledge"] = knowledge_context\n\n'''
if knowledge_block not in source:
    if insert_anchor not in source:
        raise SystemExit("knowledge insertion anchor not found")
    source = source.replace(insert_anchor, knowledge_block + insert_anchor, 1)

path.write_text(source, encoding="utf-8")

# Add a compact regression that protects the key architecture: KB enters verified
# response context after grounding, never the semantic catalog.
test = Path("backend/tests/test_clinic_knowledge_agent_contract.py")
test.write_text('''from inspect import getsource\n\nfrom app.services import agent_chat\n\n\ndef test_curated_knowledge_is_prefetched_only_after_grounding() -> None:\n    source = getsource(agent_chat._run_after_inbound)\n    semantic_call = source.index("interpret_customer_turn(")\n    knowledge_call = source.index("relevant_knowledge_context(")\n    assert knowledge_call > semantic_call\n    assert 'prefetched_results["clinic_knowledge"]' in source\n    assert 'include_clinic=include_clinic_knowledge' in source\n\n\ndef test_knowledge_does_not_enter_semantic_catalog_builder() -> None:\n    source = getsource(agent_chat._run_after_inbound)\n    catalog_section = source[source.index("clinic_catalog = build_clinic_catalog"):source.index("interpret_customer_turn(")]\n    assert "relevant_knowledge_context" not in catalog_section\n''', encoding="utf-8")
