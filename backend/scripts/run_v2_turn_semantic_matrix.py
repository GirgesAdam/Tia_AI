from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage

from app.agents.v2.semantic_context import build_semantic_context
from app.agents.v2.turn_interpreter import interpret_customer_turn_v2


CATALOG = {
    "services": [
        {
            "id": "svc-underarm",
            "name": "ليزر إبط",
            "category": "laser",
            "requires_laser_device": True,
            "laser_devices": [
                {"device_key": "candela_gentle", "device_name": "Candela Gentle"},
                {"device_key": "prime_lase", "device_name": "Prime Lase"},
            ],
        },
        {
            "id": "svc-bikini",
            "name": "ليزر بكيني",
            "category": "laser",
            "requires_laser_device": True,
            "laser_devices": [
                {"device_key": "candela_gentle", "device_name": "Candela Gentle"}
            ],
        },
    ],
    "doctors": [
        {
            "id": "doc-maryam",
            "name": "مريم",
            "service_ids": ["svc-underarm", "svc-bikini"],
        },
        {
            "id": "doc-sarah",
            "name": "سارة",
            "service_ids": ["svc-underarm"],
        },
    ],
    "appointments": [
        {
            "appointment_id": "apt-1",
            "service_id": "svc-underarm",
            "doctor_id": "doc-maryam",
            "status": "confirmed",
            "start_local": "2026-09-17T19:00:00+03:00",
        }
    ],
}


CASES = (
    "الساعة 7 متاحة؟",
    "عايزة أثبت الخميس الساعة 7 مع د مريم",
    "دفعت كام آخر مرة؟",
    "أنا دفعت أكتر من المبلغ المسجل عندكم",
    "ينفع أعمل ليزر وأنا حامل؟",
    "مش عايزة رسائل عروض تاني",
    "سعر الإبط وإيه المواعيد المتاحة السبت؟",
    "عايزة إبط وبكيني الأسبوع الجاي",
)


def main() -> None:
    timezone_name = "Africa/Cairo"
    now = datetime.now(ZoneInfo(timezone_name))
    context = build_semantic_context(CATALOG)

    for customer_text in CASES:
        decision = interpret_customer_turn_v2(
            history=[HumanMessage(content=customer_text)],
            semantic_context=context,
            timezone_name=timezone_name,
            local_now=now,
        )
        print("=" * 80)
        print(customer_text)
        print(
            json.dumps(
                decision.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
