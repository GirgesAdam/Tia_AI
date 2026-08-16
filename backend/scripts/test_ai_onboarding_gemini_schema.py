from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.onboarding_planner import plan_onboarding_turn
from app.core.config import settings
from app.agents.structured_output import canonicalize_gemini_json_schema
from app.schemas.onboarding_provider import OnboardingProviderDecision


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _semantic_depth(value) -> int:
    if not isinstance(value, dict):
        return 0
    node_type = value.get("type")
    if node_type == "array":
        return 1 + _semantic_depth(value.get("items", {}))
    if node_type == "object":
        properties = value.get("properties", {})
        return 1 + max(
            (_semantic_depth(item) for item in properties.values()),
            default=0,
        )
    if isinstance(node_type, list):
        non_null = [item for item in node_type if item != "null"]
        if "object" in non_null:
            properties = value.get("properties", {})
            return 1 + max(
                (_semantic_depth(item) for item in properties.values()),
                default=0,
            )
    return 1


def main() -> int:
    raw = OnboardingProviderDecision.model_json_schema()
    provider = canonicalize_gemini_json_schema(raw)
    keys = set(_walk_keys(provider))

    forbidden = {"$defs", "$ref", "anyOf"}
    if keys & forbidden:
        print("[FAIL] Provider schema still contains unsupported union/reference syntax")
        print("found:", sorted(keys & forbidden))
        return 2

    print("[PASS] Provider schema canonicalization")
    print("primary_model:", settings.gemini_onboarding_model)
    print("fallback_model:", settings.gemini_onboarding_fallback_model)
    print("max_output_tokens:", settings.gemini_onboarding_max_output_tokens)
    print(
        "schema_chars:",
        len(json.dumps(provider, ensure_ascii=False)),
    )
    print("semantic_depth:", _semantic_depth(provider))

    decision = plan_onboarding_turn(
        message=(
            "عندي فرعين، فرع مدينة نصر وفرع التجمع الخامس، الاتنين شغالين "
            "من 10 الصبح لـ10 بالليل كل يوم. عندي دكتور أحمد محمود ودكتورة "
            "سارة علي. ضيف خدمة ليزر إزالة الشعر سعرها 1500 جنيه ومدتها ساعة، "
            "وخلي الدكاترة متاحين للخدمة في الفرعين. الحجز كل 15 دقيقة، "
            "مسموح حجز نفس اليوم، ولازم تأكيد الحجز."
        ),
        current_setup={
            "branches": [],
            "services": [],
            "doctors": [],
            "booking_settings_exists": False,
        },
        stored_plan={},
        recent_history=[],
    )

    print("[PASS] Gemini onboarding structured request accepted")
    print("action:", decision.action)
    print("capabilities:", decision.capabilities)
    print("branches:", len(decision.plan.branches))
    print("services:", len(decision.plan.services))
    print("doctors:", len(decision.plan.doctors))
    print(
        "branch_hours:",
        sum(len(item.working_hours) for item in decision.plan.branches),
    )
    print(
        "doctor_hour_groups:",
        sum(len(item.working_hours) for item in decision.plan.doctors),
    )
    print("booking_settings:", decision.plan.booking_settings.apply)
    print("missing_information:", decision.missing_information)
    print("assistant_message:", decision.assistant_message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
