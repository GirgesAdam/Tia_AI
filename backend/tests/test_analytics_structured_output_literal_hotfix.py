from app.agents.structured_output import canonicalize_provider_json_schema
from app.schemas.analytics_composable import AnalyticsComposePlan


def test_composable_analytics_provider_schema_keeps_literal_discriminators() -> None:
    schema = canonicalize_provider_json_schema(AnalyticsComposePlan.model_json_schema())

    business_kind = schema["properties"]["business_plan"]["properties"]["kind"]
    audience_kind = schema["properties"]["audience_plan"]["properties"]["kind"]

    assert business_kind["type"] == "string"
    assert business_kind["enum"] == ["business_analytics"]
    assert audience_kind["type"] == "string"
    assert audience_kind["enum"] == ["patient_audience"]
