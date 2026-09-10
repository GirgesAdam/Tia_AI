from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.turn_interpreter import interpret_customer_turn
from scripts.run_realistic_system_journeys import TokenMeter


LASER_SERVICE_ID = "22222222-2222-4222-8222-222222222222"
HYDRA_SERVICE_ID = "11111111-1111-4111-8111-111111111111"
LASER_APPOINTMENT_ID = "44444444-4444-4444-8444-444444444444"
HYDRA_APPOINTMENT_ID = "33333333-3333-4333-8333-333333333333"
LASER_DOCTOR_ID = "66666666-6666-4666-8666-666666666666"
HYDRA_DOCTOR_ID = "55555555-5555-4555-8555-555555555555"


def main() -> None:
    catalog = {
        "services": [
            {
                "id": LASER_SERVICE_ID,
                "service_id": LASER_SERVICE_ID,
                "name": "ليزر إزالة الشعر - إبط",
                "service_name": "ليزر إزالة الشعر - إبط",
                "requires_laser_device": True,
            },
            {
                "id": HYDRA_SERVICE_ID,
                "service_id": HYDRA_SERVICE_ID,
                "name": "هيدرافيشل",
                "service_name": "هيدرافيشل",
                "requires_laser_device": False,
            },
        ],
        "doctors": [
            {
                "id": LASER_DOCTOR_ID,
                "doctor_id": LASER_DOCTOR_ID,
                "name": "أحمد محمود",
                "doctor_name": "أحمد محمود",
                "service_ids": [LASER_SERVICE_ID],
            },
            {
                "id": HYDRA_DOCTOR_ID,
                "doctor_id": HYDRA_DOCTOR_ID,
                "name": "هالة مصطفى",
                "doctor_name": "هالة مصطفى",
                "service_ids": [HYDRA_SERVICE_ID],
            },
        ],
        "appointments": [
            {
                "id": LASER_APPOINTMENT_ID,
                "appointment_id": LASER_APPOINTMENT_ID,
                "service_id": LASER_SERVICE_ID,
                "service_name": "ليزر إزالة الشعر - إبط",
                "doctor_id": LASER_DOCTOR_ID,
                "doctor_name": "أحمد محمود",
                "status": "confirmed",
                "start_local": "2026-09-11T14:00:00+03:00",
                "end_local": "2026-09-11T14:15:00+03:00",
                "laser_device_key": "prime_lase",
                "laser_device_name": "Prime Lase",
            },
            {
                "id": HYDRA_APPOINTMENT_ID,
                "appointment_id": HYDRA_APPOINTMENT_ID,
                "service_id": HYDRA_SERVICE_ID,
                "service_name": "هيدرافيشل",
                "doctor_id": HYDRA_DOCTOR_ID,
                "doctor_name": "هالة مصطفى",
                "status": "confirmed",
                "start_local": "2026-09-12T10:00:00+03:00",
                "end_local": "2026-09-12T11:00:00+03:00",
                "laser_device_key": None,
                "laser_device_name": None,
            },
        ],
        "branches": [],
    }
    history = [
        HumanMessage(content="عايز ألغي معاد عندي."),
        AIMessage(
            content=(
                "عندك معادين مؤكدين، تحب تلغي أنهي واحد؟\n\n"
                "1. ليزر إزالة الشعر - إبط: النهارده 11 سبتمبر الساعة 2:00 م\n"
                "2. هيدرافيشل: السبت 12 سبتمبر الساعة 10:00 ص"
            )
        ),
        HumanMessage(content="قصدي معاد الهيدرافيشل، سيب معاد الليزر زي ما هو."),
    ]

    meter = TokenMeter()
    meter.install()
    mark = meter.mark()
    try:
        decision = interpret_customer_turn(
            flow=None,
            history=history,
            timezone_name="Africa/Cairo",
            local_now=datetime(2026, 9, 11, 0, 15, tzinfo=ZoneInfo("Africa/Cairo")),
            clinic_catalog=catalog,
        )
    finally:
        usage = meter.since(mark)
        meter.uninstall()

    print(
        json.dumps(
            {
                "decision": decision.model_dump(mode="json"),
                "tokens": usage,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
