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
    """Apply invariant-only defense-in-depth to customer-visible output.

    Tone and semantic decisions belong to the model/prompt and orchestration layers.
    This final guard intentionally does not rewrite language or reinterpret intent;
    it only removes identifier shapes that must never be exposed to customers.
    """
    text = reply.strip()
    text = _DOCTOR_SHORT_ID.sub("الدكتور المتاح", text)
    text = _BRANCH_SHORT_ID.sub("الفرع المتاح", text)
    text = _SERVICE_SHORT_ID.sub("الخدمة", text)
    text = _FULL_UUID.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip()
