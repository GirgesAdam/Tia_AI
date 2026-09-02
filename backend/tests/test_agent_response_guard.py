from app.agents.response_guard import sanitize_customer_reply


def test_full_uuid_is_removed() -> None:
    reply = "الدكتور 50c4d2be-20de-4b06-8dbf-7e9425faebc4 متاح الساعة 8"
    cleaned = sanitize_customer_reply(reply)
    assert "50c4d2be" not in cleaned


def test_short_entity_ids_are_replaced_without_exposing_identifiers() -> None:
    assert sanitize_customer_reply("الدكتور 50c4d2be متاح الساعة 8") == "الدكتور المتاح متاح الساعة 8"
    assert sanitize_customer_reply("الفرع deadbeef متاح") == "الفرع المتاح متاح"
    assert sanitize_customer_reply("الخدمة cafe1234 متاحة") == "الخدمة متاحة"


def test_guard_does_not_rewrite_tone_or_semantics() -> None:
    reply = (
        "أعتذر، لكن هذا الموضوع يحتاج تقييم طبي مباشر. "
        "لقد حولت المحادثة للفريق، وسيتواصل معك قريبًا."
    )
    assert sanitize_customer_reply(reply) == reply
