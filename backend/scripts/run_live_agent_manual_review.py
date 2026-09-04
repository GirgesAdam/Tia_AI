from __future__ import annotations

"""Run only explicitly requested live Agent conversations for manual UX review.

This runner intentionally does not assign PASS/FAIL quality labels. It reuses the
rollback-isolated scenario fixtures from ``run_live_agent_ux_review`` only to
create realistic conversations and collect their transcripts. Conversation
quality is judged by reading the actual assistant replies.

There is deliberately no default scenario list: callers must name every case
with ``--case`` so previously accepted conversations are not rerun by accident.
"""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from app.core.config import settings
from scripts.run_live_agent_ux_review import _execute_case


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-slug", default="tia")
    parser.add_argument(
        "--report",
        default="artifacts/live-agent-manual-review.json",
    )
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        required=True,
        help="Scenario to run. Repeat --case for additional NEW/changed scenarios only.",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    started = datetime.now(UTC).isoformat()
    transcripts: list[dict[str, object]] = []
    technical_errors = 0

    try:
        for index, name in enumerate(args.cases, start=1):
            print(f"[{index:02d}/{len(args.cases)}] {name}", flush=True)
            fixture_result = _execute_case(engine, args.workspace_slug, name)
            error = fixture_result.error
            if error:
                technical_errors += 1
            transcripts.append(
                {
                    "name": name,
                    "execution_error": error,
                    "turns": [asdict(turn) for turn in fixture_result.turns],
                }
            )
            print("  -> transcript captured" if not error else f"  -> execution error: {error}", flush=True)
    finally:
        engine.dispose()

    payload = {
        "started_at": started,
        "workspace_slug": args.workspace_slug,
        "conversation_count": len(transcripts),
        "quality_scoring": "manual_transcript_review",
        "database_writes_persisted": False,
        "whatsapp_or_n8n_used": False,
        "results": transcripts,
    }
    path = Path(args.report)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {path}", flush=True)
    return 1 if technical_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
