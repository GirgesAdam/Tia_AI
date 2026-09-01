from app.agents.response_guard import sanitize_customer_reply


def test_full_uuid_is_removed() -> None:
    reply = "الدكتور 50c4d2be-20de-4b06-8dbf-7e9425faebc4 متاح الساعة 8"
    cleaned = sanitize_customer_reply(reply)
    assert "50c4d2be" not in cleaned


def test_short_doctor_id_is_replaced() -> None:
    cleaned = sanitize_customer_reply("الدكتور 50c4d2be متاح الساعة 8")
    assert cleaned == "الدكتور المتاح متاح الساعة 8"


def test_common_fusha_handoff_is_softened() -> None:
    cleaned = sanitize_customer_reply(
        "أعتذر، لكن هذا الموضوع يحتاج تقييم طبي مباشر. "
        "لقد حولت المحادثة للفريق، وسيتواصل معك قريبًا."
    )
    assert "أعتذر" not in cleaned
    assert "هذا الموضوع يحتاج" not in cleaned
    assert "لقد" not in cleaned
    assert "سيتواصل معك" not in cleaned
    assert "الموضوع ده محتاج" in cleaned
