from __future__ import annotations

from typing import Any


def summary_from_rows(
    rows: list[dict[str, Any]],
    *,
    duration_seconds: float = 0.0,
) -> dict[str, Any]:
    failed = [
        row for row in rows
        if row.get("issues") or row.get("execution_error")
    ]
    severities = {f"P{level}": 0 for level in range(4)}
    for row in rows:
        for issue in row.get("issues") or ():
            severity = issue.get("severity")
            if severity in severities:
                severities[severity] += 1
    tokens = sum(
        int((row.get("token_usage") or {}).get("total_tokens") or 0)
        for row in rows
    )
    cost = sum(
        float((row.get("cost") or {}).get("actual_total_usd") or 0.0)
        for row in rows
    )
    return {
        "Total scenarios": len(rows),
        "Passed": len(rows) - len(failed),
        "Failed": len(failed),
        **severities,
        "Tokens": tokens,
        "Cost": round(cost, 8),
        "Duration": round(duration_seconds, 2),
    }


def print_summary(data: dict[str, Any]) -> None:
    print("Unified evaluation summary")
    for key, value in data.items():
        print(f"{key}: {value}")
