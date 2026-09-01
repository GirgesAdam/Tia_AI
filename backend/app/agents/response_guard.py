from __future__ import annotations

import re

_FULL_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)

_DOCTOR_SHORT_ID = re.compile(r"(?i)\b(الدكتور|الطبيب|doctor)\s+[0-9a-f]{8,32}\b")

_BRANCH_SHORT_ID = re.compile(r"(?i)\b(الفرع|branch)\s+[0-9a-f]{8,32}\b")

_SERVICE_SHORT_ID = re.compile(r"(?i)\b(الخدمة|service)\s+[0-9a-f]{8,32}\b")


def sanitize_customer_reply(reply: str) -> str:
    """
    Last-line customer-output guard.

    The model should already follow the Egyptian-Arabic and no-internal-ID prompt.
    This function is only defense-in-depth for accidental identifier leakage and
    a few high-frequency formal Arabic phrases observed during staging tests.
    """
    text = reply.strip()

    text = _DOCTOR_SHORT_ID.sub("الدكتور المتاح", text)
    text = _BRANCH_SHORT_ID.sub("الفرع المتاح", text)
    text = _SERVICE_SHORT_ID.sub("الخدمة", text)
    text = _FULL_UUID.sub("", text)

    replacements = {
        "أعتذر، لكن": "معلش،",
        "أعتذر لكن": "معلش،",
        "أعتذر،": "معلش،",
        "أعتذر": "معلش",
        "لقد حولت المحادثة": "حوّلت المحادثة",
        "لقد حوّلت المحادثة": "حوّلت المحادثة",
        "هذا الموضوع يحتاج": "الموضوع ده محتاج",
        "هذا الموضوع محتاج": "الموضوع ده محتاج",
        "سيتواصل معك قريباً": "والفريق هيكمل المتابعة من هنا",
        "سيتواصل معك قريبًا": "وحوّلت المحادثة لفريق العيادة للمراجعة",
        "هينسق معاك قريب": "وحوّلت المحادثة لفريق العيادة للمراجعة",
        "هينسق معاكي قريب": "وحوّلت المحادثة لفريق العيادة للمراجعة",
        "حأحولك": "هحوّلك",
        "أخبريني": "قوليلي",
        "أخبرني": "قولي",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip()
