from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from app.core.config import settings
from scripts.run_v2_realistic_round2 import _execute_general

CASES = (
    "price_duration_round2",
    "doctor_availability_round2",
)


def main() -> int:
    if not settings.agent_v2_live_enabled:
        raise RuntimeError("Focused round-two rerun requires AGENT_V2_LIVE_ENABLED=true.")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        results = [_execute_general(engine, "tia", name) for name in CASES]
    finally:
        engine.dispose()

    payload = {
        "started_at": datetime.now(UTC).isoformat(),
        "runtime": "v2",
        "database_writes_persisted": False,
        "whatsapp_or_n8n_used": False,
        "results": [asdict(item) for item in results],
    }
    path = Path("artifacts/v2-realistic-round2-focus.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for result in results:
        print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")), flush=True)
    print(f"Report: {path}", flush=True)
    return 1 if any(result.error for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
