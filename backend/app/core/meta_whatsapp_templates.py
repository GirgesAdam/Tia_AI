from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TemplateCategory = Literal["UTILITY", "MARKETING"]


@dataclass(frozen=True)
class StandardWhatsAppTemplate:
    rule_key: str
    label_ar: str
    name: str
    language: str
    category: TemplateCategory
    body_text: str
    example_body_parameters: tuple[str, ...]


STANDARD_WHATSAPP_TEMPLATES: tuple[StandardWhatsAppTemplate, ...] = (
    StandardWhatsAppTemplate(
        rule_key="booking_confirmation",
        label_ar="تأكيد الحجز (ثابت)",
        name="tia_booking_confirmation_ar",
        language="ar_EG",
        category="UTILITY",
        body_text=(
            "تمام يا {{1}}، حجز {{2}} اتسجل يوم {{3}} الساعة {{4}} في {{5}}. "
            "لو حابة تغيّري أي حاجة ابعتيلي هنا."
        ),
        example_body_parameters=("مريم", "ليزر", "12/09/2026", "17:00", "Tia Clinic"),
    ),
    StandardWhatsAppTemplate(
        rule_key="appointment_reminder_6h",
        label_ar="تذكير قبل الموعد",
        name="tia_reminder_01",
        language="ar_EG",
        category="UTILITY",
        body_text="أهلًا {{1}} 👋 بفكرك إن عندك جلسة {{2}} الساعة {{3}}. مستنيينك 💛",
        example_body_parameters=("مريم", "ليزر", "17:00"),
    ),
    StandardWhatsAppTemplate(
        rule_key="post_visit_followup",
        label_ar="متابعة بعد الزيارة",
        name="tia_post_visit_01",
        language="ar_EG",
        category="UTILITY",
        body_text="إزيك {{1}}؟ حبيت أطمن عليكي بعد {{2}} اللي كانت يوم {{3}}. كل حاجة تمام؟",
        example_body_parameters=("مريم", "ليزر", "12/09/2026"),
    ),
    StandardWhatsAppTemplate(
        rule_key="cancellation_recovery",
        label_ar="متابعة بعد الإلغاء",
        name="tia_cancellation_recovery_ar",
        language="ar_EG",
        category="UTILITY",
        body_text=(
            "أهلًا {{1}}، حبيت أساعدك بعد إلغاء موعد {{2}} يوم {{3}} الساعة {{4}}. "
            "لو حابة نرتب ميعاد جديد ابعتيلي هنا وأنا أساعدك."
        ),
        example_body_parameters=("مريم", "ليزر", "12/09/2026", "17:00"),
    ),
    StandardWhatsAppTemplate(
        rule_key="lead_not_booked_followup",
        label_ar="متابعة العميل اللي ماحجزش",
        name="tia_ai_followup_ar",
        language="ar_EG",
        category="MARKETING",
        body_text=(
            "أهلًا {{1}}، بنتابع معاكي بخصوص {{2}}. آخر متابعة كانت يوم {{3}} الساعة {{4}} من {{5}}. "
            "لو حابة تكملي الحجز ابعتيلي هنا."
        ),
        example_body_parameters=("مريم", "استفسار عن الليزر", "12/09/2026", "17:00", "Tia Clinic"),
    ),
)

STANDARD_TEMPLATE_BY_RULE_KEY = {
    template.rule_key: template for template in STANDARD_WHATSAPP_TEMPLATES
}


def template_create_payload(template: StandardWhatsAppTemplate) -> dict[str, object]:
    return {
        "name": template.name,
        "language": template.language,
        "category": template.category,
        "components": [
            {
                "type": "BODY",
                "text": template.body_text,
                "example": {"body_text": [list(template.example_body_parameters)]},
            }
        ],
    }
