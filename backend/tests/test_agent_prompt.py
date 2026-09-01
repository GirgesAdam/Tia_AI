from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.prompts.customer_service import build_customer_service_system_prompt


def test_customer_agent_defaults_to_egyptian_arabic() -> None:
    prompt = build_customer_service_system_prompt(
        clinic_name="Tia",
        timezone_name="Africa/Cairo",
        local_now=datetime(2026, 8, 12, 18, 0, tzinfo=ZoneInfo("Africa/Cairo")),
    )
    assert "العربي المصري" in prompt
    assert 'ما تقولش "حجزت"' in prompt
    assert "escalate_to_human" in prompt
    assert "create_follow_up_task" in prompt
    assert "مش دكتور" in prompt
    assert "18:00" in prompt
    assert "start_time_24h" in prompt


def test_prompt_blocks_internal_ids_and_fusha() -> None:
    prompt = build_customer_service_system_prompt(
        clinic_name="Tia", timezone_name="Africa/Cairo", local_now=datetime(2026, 8, 12, 20, 0)
    )
    assert "UUIDs" in prompt
    assert "أعتذر" in prompt
    assert "المصري" in prompt
