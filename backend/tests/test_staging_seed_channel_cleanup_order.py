from pathlib import Path


def test_seed_cleans_conversations_by_seed_owned_channel_before_connection_delete() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/seed_full_staging_demo.py").read_text(encoding="utf-8")

    conversation_filter = "Conversation.channel_connection_id.in_(connection_ids)"
    connection_delete = "delete(ChannelConnection).where("

    assert conversation_filter in source
    assert connection_delete in source
    assert source.index(conversation_filter) < source.index(connection_delete)


def test_seed_still_cleans_conversations_by_seed_patient_ids() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/seed_full_staging_demo.py").read_text(encoding="utf-8")

    assert "Conversation.patient_id.in_(patient_ids)" in source
