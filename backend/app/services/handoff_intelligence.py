from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

HANDOFF_CONTEXT_SCHEMA_VERSION = 1
_CONTEXT_TRIGGERS = {"semantic_policy", "agent_tool", "manual_takeover", "system"}


def _clean_text(value: object, *, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    if not text:
        return None
    return text[:limit]


def _clean_list(values: object, *, item_limit: int, max_items: int) -> list[str]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, Mapping)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value, limit=item_limit)
        if text is None or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def build_handoff_context(
    *,
    trigger: str,
    semantic_reason: object = None,
    confidence: object = None,
    risk_flags: object = None,
    capabilities: object = None,
    latest_customer_message: object = None,
    flow_type: object = None,
    flow_status: object = None,
    missing_information: object = None,
) -> dict[str, Any]:
    """Build a bounded staff-facing escalation snapshot without another LLM call.

    Inputs are observations already produced by the semantic turn plus deterministic
    workflow state. The function deliberately accepts primitives so it can remain
    independent from provider/LangChain runtime imports.
    """
    normalized_trigger = str(trigger).strip().lower()
    if normalized_trigger not in _CONTEXT_TRIGGERS:
        normalized_trigger = "system"

    parsed_confidence: float | None = None
    if confidence is not None:
        try:
            numeric = float(confidence)
        except (TypeError, ValueError):
            numeric = -1.0
        if 0.0 <= numeric <= 1.0:
            parsed_confidence = round(numeric, 4)

    flow: dict[str, Any] = {}
    cleaned_flow_type = _clean_text(flow_type, limit=80)
    cleaned_flow_status = _clean_text(flow_status, limit=80)
    cleaned_missing = _clean_list(missing_information, item_limit=160, max_items=12)
    if cleaned_flow_type:
        flow["type"] = cleaned_flow_type
    if cleaned_flow_status:
        flow["status"] = cleaned_flow_status
    if cleaned_missing:
        flow["missing_information"] = cleaned_missing

    context: dict[str, Any] = {
        "schema_version": HANDOFF_CONTEXT_SCHEMA_VERSION,
        "trigger": normalized_trigger,
        "risk_flags": _clean_list(risk_flags, item_limit=60, max_items=8),
        "capabilities": _clean_list(capabilities, item_limit=80, max_items=20),
    }
    reason = _clean_text(semantic_reason, limit=1200)
    if reason:
        context["semantic_reason"] = reason
    if parsed_confidence is not None:
        context["confidence"] = parsed_confidence
    last_message = _clean_text(latest_customer_message, limit=1600)
    if last_message:
        context["latest_customer_message"] = last_message
    if flow:
        context["flow"] = flow
    return context


def normalize_handoff_context(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {}
    flow = value.get("flow") if isinstance(value.get("flow"), Mapping) else {}
    context = build_handoff_context(
        trigger=str(value.get("trigger") or "system"),
        semantic_reason=value.get("semantic_reason"),
        confidence=value.get("confidence"),
        risk_flags=value.get("risk_flags"),
        capabilities=value.get("capabilities"),
        latest_customer_message=value.get("latest_customer_message"),
        flow_type=flow.get("type"),
        flow_status=flow.get("status"),
        missing_information=flow.get("missing_information"),
    )
    first_trigger = _clean_text(value.get("first_trigger"), limit=40)
    if first_trigger in _CONTEXT_TRIGGERS:
        context["first_trigger"] = first_trigger
    try:
        escalation_count = int(value.get("escalation_count", 1))
    except (TypeError, ValueError):
        escalation_count = 1
    context["escalation_count"] = max(1, min(escalation_count, 1000))
    return context


def merge_handoff_context(existing: object, incoming: object) -> dict[str, Any]:
    old = normalize_handoff_context(existing)
    new = normalize_handoff_context(incoming)
    if not old:
        if not new:
            return {}
        new["first_trigger"] = new.get("trigger", "system")
        new["escalation_count"] = 1
        return new
    if not new:
        return old

    merged = dict(old)
    merged["schema_version"] = HANDOFF_CONTEXT_SCHEMA_VERSION
    merged["trigger"] = new.get("trigger", old.get("trigger", "system"))

    for key in ("semantic_reason", "confidence", "latest_customer_message", "flow"):
        if key in new:
            merged[key] = new[key]

    merged["risk_flags"] = _clean_list(
        [*(old.get("risk_flags") or []), *(new.get("risk_flags") or [])],
        item_limit=60,
        max_items=8,
    )
    merged["capabilities"] = _clean_list(
        [*(old.get("capabilities") or []), *(new.get("capabilities") or [])],
        item_limit=80,
        max_items=20,
    )

    material_keys = (
        "trigger",
        "semantic_reason",
        "confidence",
        "latest_customer_message",
        "flow",
        "risk_flags",
        "capabilities",
    )
    if all(merged.get(key) == old.get(key) for key in material_keys):
        return old

    merged["first_trigger"] = old.get("first_trigger") or old.get("trigger") or "system"
    merged["escalation_count"] = min(int(old.get("escalation_count", 1)) + 1, 1000)
    return merged
