from __future__ import annotations

import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
WORKFLOWS = PROJECT_DIR / "n8n" / "workflows"


def load(name: str) -> dict:
    return json.loads((WORKFLOWS / name).read_text(encoding="utf-8"))


def main() -> int:
    scheduler = load("tia_automation_scheduler.json")
    scheduler_raw = json.dumps(scheduler, ensure_ascii=False)
    assert scheduler.get("nodes")
    assert "$env.TIA_API_BASE_URL" in scheduler_raw
    assert "/api/v1/automations/adapter/" in scheduler_raw
    assert "/api/v1/automations/adapter/clinic-sync/tick" in scheduler_raw
    assert "/adapter/outbox/claim" not in scheduler_raw
    assert "n8n-nodes-base.whatsApp" not in scheduler_raw
    print("[PASS] Oracle scheduler contract")

    transport_waker = load("tia_whatsapp_outbox_worker.json")
    waker_raw = json.dumps(transport_waker, ensure_ascii=False)
    assert transport_waker.get("nodes")
    assert "/api/v1/channels/whatsapp/transport/tick" in waker_raw
    assert "/adapter/outbox/claim" not in waker_raw
    assert "/adapter/outbox/provider-status" not in waker_raw
    assert "n8n-nodes-base.whatsApp" not in waker_raw
    assert "graph.facebook.com" not in waker_raw
    print("[PASS] Native WhatsApp waker contract")

    assert not (WORKFLOWS / "tia_whatsapp_inbound_status.json").exists()
    assert not (WORKFLOWS / "tia_gmail_outbox_worker.json").exists()
    print("[PASS] Retired inbound/Gmail workflows absent")

    docs = (PROJECT_DIR / "n8n" / "REAL_RUNTIME_SETUP.md").read_text(encoding="utf-8")
    assert "tia-whatsapp-transport-waker" in docs
    assert "tia_automation_scheduler.json" in docs
    assert "n8n WhatsApp Trigger" not in docs
    print("[PASS] Runtime documentation matches native transport")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
