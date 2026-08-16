from __future__ import annotations

import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
WORKFLOWS = PROJECT_DIR / "n8n" / "workflows"


def load(name: str) -> dict:
    return json.loads((WORKFLOWS / name).read_text(encoding="utf-8"))


def main() -> int:
    names = (
        "tia_whatsapp_inbound_status.json",
        "tia_whatsapp_outbox_worker.json",
        "tia_automation_scheduler.json",
        "tia_gmail_outbox_worker.json",
    )
    for name in names:
        workflow = load(name)
        assert workflow.get("nodes"), name
        raw = json.dumps(workflow, ensure_ascii=False)
        assert "YOUR_TIA_BACKEND_DOMAIN" in raw, name
        assert "adapter_token" not in raw.lower(), name
        assert "worker_token" not in raw.lower(), name
        assert "access_token" not in raw.lower(), name
        assert "api_key" not in raw.lower(), name
        print(f"[PASS] workflow contract: {name}")

    gmail = load("tia_gmail_outbox_worker.json")
    gmail_nodes = {node["name"]: node for node in gmail["nodes"]}
    assert gmail_nodes["Gmail Send Message"]["type"] == "n8n-nodes-base.gmail"
    assert gmail_nodes["Gmail Send Message"]["typeVersion"] >= 2.2
    assert gmail_nodes["Gmail Send Message"]["retryOnFail"] is True
    print("[PASS] Gmail send/retry contract")

    whatsapp = load("tia_whatsapp_inbound_status.json")
    assert any(node["type"] == "n8n-nodes-base.whatsAppTrigger" for node in whatsapp["nodes"])
    print("[PASS] WhatsApp trigger contract")

    scheduler = load("tia_automation_scheduler.json")
    assert any(
        node["name"] == "Every Minute" and node["type"] == "n8n-nodes-base.scheduleTrigger"
        for node in scheduler["nodes"]
    )
    print("[PASS] Automation scheduler contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
