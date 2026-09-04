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
            'x-automation-token":',
            'access_token":',
            'client_secret":',
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


def test_whatsapp_result_nodes_avoid_optional_chaining_expression_parser_bug() -> None:
    path = _root() / "n8n" / "workflows" / "tia_whatsapp_outbox_worker.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    by_name = {node["name"]: node for node in workflow["nodes"]}

    for name in ("Tia Record Template Result", "Tia Record Text Result"):
        node = by_name[name]
        body = node["parameters"]["jsonBody"]
        url = node["parameters"]["url"]
        assert "?." not in body
        assert "$('Expand Dispatches').item.json.dispatch_id" in url
        assert "/adapter/outbox/" in url
        assert "/result" in url


def test_whatsapp_provider_send_is_single_attempt_and_preserves_real_error() -> None:
    path = _root() / "n8n" / "workflows" / "tia_whatsapp_outbox_worker.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    by_name = {node["name"]: node for node in workflow["nodes"]}

    send_nodes = [
        name
        for name in by_name
        if name == "WhatsApp Send Text" or name.startswith("WhatsApp Send Template")
    ]
    assert send_nodes
    for name in send_nodes:
        node = by_name[name]
        assert node.get("retryOnFail") is not True
        assert "maxTries" not in node

    for name in ("Tia Record Template Result", "Tia Record Text Result"):
        body = by_name[name]["parameters"]["jsonBody"]
        assert "typeof $json.error" not in body
        assert "$json.error.toString()" in body
        assert "errorDescription" in body
        assert "retry_after_seconds" in body


def test_runtime_workers_support_a_hosted_backend_url() -> None:
    root = _root() / "n8n" / "workflows"
    for name in ("tia_automation_scheduler.json", "tia_whatsapp_outbox_worker.json"):
        raw = (root / name).read_text(encoding="utf-8")
        assert "$env.TIA_API_BASE_URL" in raw
        # Local Docker remains a fallback, not the only backend address.
        assert "|| 'http://host.docker.internal:8000'" in raw


def test_automation_scheduler_execute_url_is_a_real_expression() -> None:
    path = _root() / "n8n" / "workflows" / "tia_automation_scheduler.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    by_name = {node["name"]: node for node in workflow["nodes"]}

    execute_url = by_name["Tia Execute Automation"]["parameters"]["url"]
    assert "$env.TIA_API_BASE_URL" in execute_url
    assert "/api/v1/automations/adapter/jobs/" in execute_url
    assert "+ $json.job_id +" in execute_url
    assert "%27%20%2B%20%24json.job_id" not in execute_url


def test_whatsapp_ai_process_is_not_blindly_retried_by_n8n() -> None:
    path = _root() / "n8n" / "workflows" / "tia_whatsapp_inbound_status.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    by_name = {node["name"]: node for node in workflow["nodes"]}

    process = by_name["Tia Process With AI"]
    assert process.get("retryOnFail") is not True
    assert "maxTries" not in process
    assert "waitBetweenTries" not in process

    # Accepting the normalized inbound is idempotent and can keep its own retry.
    assert by_name["Tia Accept Inbound"].get("retryOnFail") is True
