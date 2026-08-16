import json
from pathlib import Path


WORKFLOW_NAMES = (
    "tia_whatsapp_inbound_status.json",
    "tia_whatsapp_outbox_worker.json",
    "tia_automation_scheduler.json",
    "tia_gmail_outbox_worker.json",
)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_workflows_are_valid_json_without_embedded_credentials() -> None:
    for name in WORKFLOW_NAMES:
        path = _root() / "n8n" / "workflows" / name
        workflow = json.loads(path.read_text(encoding="utf-8"))
        assert workflow["nodes"]
        raw = json.dumps(workflow, ensure_ascii=False).lower()
        for forbidden in (
            "tia_ch_",
            "x-automation-token\":",
            "access_token\":",
            "client_secret\":",
        ):
            assert forbidden not in raw


def test_gmail_worker_reports_success_and_retryable_failure() -> None:
    path = _root() / "n8n" / "workflows" / "tia_gmail_outbox_worker.json"
    raw = path.read_text(encoding="utf-8")
    assert "n8n-nodes-base.gmail" in raw
    assert "retry_after_seconds" in raw
    assert "provider_message_id" in raw
    assert "thread_id" in raw


def test_whatsapp_workflows_have_provider_result_and_status_callback_paths() -> None:
    root = _root() / "n8n" / "workflows"
    inbound = (root / "tia_whatsapp_inbound_status.json").read_text(encoding="utf-8")
    outbox = (root / "tia_whatsapp_outbox_worker.json").read_text(encoding="utf-8")
    assert "/outbox/provider-status" in inbound
    assert "/adapter/inbound" in inbound
    assert "/result" in outbox
    assert "WhatsApp Send Template" in outbox
    assert "WhatsApp Send Text" in outbox
