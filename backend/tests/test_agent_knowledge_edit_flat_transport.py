from uuid import uuid4

from app.agents.clinic_knowledge_edit_transport import (
    _FlatKnowledgeEditDecision,
    _FlatKnowledgeEditOperation,
    _normalize_flat_decision,
    _transport_catalog,
)


def _catalog():
    service_id = str(uuid4())
    branch_id = str(uuid4())
    doctor_id = str(uuid4())
    return {
        "workspace": {"name": "Clinic", "timezone": "Africa/Cairo"},
        "services": [
            {
                "id": service_id,
                "name": "PRP للبشرة",
                "category": "بشرة",
                "duration_minutes": 30,
                "price_egp": 1500,
                "active": True,
            }
        ],
        "branches": [
            {
                "id": branch_id,
                "name": "مدينة نصر",
                "city": "القاهرة",
                "address": "عباس العقاد",
                "timezone": "Africa/Cairo",
                "active": True,
                "working_hours": [],
            }
        ],
        "doctors": [
            {
                "id": doctor_id,
                "name": "أحمد محمود",
                "specialization": "جلدية",
                "phone": None,
                "email": None,
                "booking_enabled": True,
                "active": True,
                "branches": [{"id": branch_id, "name": "مدينة نصر", "primary": True}],
                "services": [{"id": service_id, "name": "PRP للبشرة"}],
                "schedules": [],
            }
        ],
        "booking_settings": None,
    }


def test_transport_catalog_exposes_short_refs_not_uuids_to_model() -> None:
    catalog = _catalog()
    transport, ref_to_id = _transport_catalog(catalog)

    assert transport["services"][0]["ref"] == "service:0"
    assert transport["services"][0]["name"] == "PRP للبشرة"
    assert "id" not in transport["services"][0]
    assert transport["branches"][0]["ref"] == "branch:0"
    assert "id" not in transport["branches"][0]
    assert transport["doctors"][0]["ref"] == "doctor:0"
    assert "id" not in transport["doctors"][0]
    assert ref_to_id["service:0"] == catalog["services"][0]["id"]


def test_two_service_fields_in_one_admin_request_group_into_one_canonical_action() -> None:
    catalog = _catalog()
    _, ref_to_id = _transport_catalog(catalog)
    decision = _FlatKnowledgeEditDecision(
        understood=True,
        needs_clarification=False,
        assistant_message="هعدّل مدة وسعر PRP للبشرة بعد تأكيدك.",
        operations=[
            _FlatKnowledgeEditOperation(
                kind="update_service",
                target_ref="service:0",
                field="duration_minutes",
                value_type="number",
                value="45",
            ),
            _FlatKnowledgeEditOperation(
                kind="update_service",
                target_ref="service:0",
                field="price_egp",
                value_type="number",
                value="2000",
            ),
        ],
    )

    normalized = _normalize_flat_decision(decision, ref_to_id=ref_to_id)

    assert normalized.understood is True
    assert normalized.needs_clarification is False
    assert len(normalized.actions) == 1
    action = normalized.actions[0]
    assert action.kind == "update_service"
    assert action.entity_id == catalog["services"][0]["id"]
    assert [(change.field, change.number_value) for change in action.changes] == [
        ("duration_minutes", 45.0),
        ("price_egp", 2000.0),
    ]


def test_flat_provider_schema_has_no_nested_canonical_actions_or_uuid_fields() -> None:
    schema = _FlatKnowledgeEditDecision.model_json_schema()
    serialized = str(schema)
    assert "operations" in serialized
    assert "changes" not in serialized
    assert "schedule" not in serialized
    assert "entity_id" not in serialized
    assert "branch_id" not in serialized
    assert "target_ref" in serialized
    # Keep Gemini transport in the same provider-safe subset that already works
    # for clinic mapping: no nullable unions or strict additionalProperties.
    assert "anyOf" not in serialized
    assert "additionalProperties" not in serialized
    assert "number_value" not in serialized
    assert "bool_value" not in serialized
    assert "value_type" in serialized
    assert "value" in serialized
