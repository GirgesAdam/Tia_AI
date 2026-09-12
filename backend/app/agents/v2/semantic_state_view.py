from __future__ import annotations

from typing import Any

from app.agents.v2.semantic_context import ReferenceKind, SemanticContext


def _reverse_refs(context: SemanticContext, kind: ReferenceKind) -> dict[str, str]:
    return {
        target.canonical_id: ref
        for ref, target in context.reference_map.items()
        if target.kind == kind
    }


def _entity_ref(
    value: object,
    *,
    kind: ReferenceKind,
    context: SemanticContext,
) -> str | None:
    if value in (None, ""):
        return None
    return _reverse_refs(context, kind).get(str(value))


def _entity_refs(
    value: object,
    *,
    kind: ReferenceKind,
    context: SemanticContext,
) -> list[str]:
    if not isinstance(value, list):
        return []
    reverse = _reverse_refs(context, kind)
    return [reverse[str(item)] for item in value if str(item) in reverse]


def _safe_constraints(value: object, context: SemanticContext) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, object] = {}
    mappings: tuple[tuple[str, ReferenceKind, str], ...] = (
        ("service_id", "service", "service_ref"),
        ("doctor_id", "doctor", "doctor_ref"),
        ("device_key", "device", "device_ref"),
    )
    for input_key, kind, output_key in mappings:
        ref = _entity_ref(value.get(input_key), kind=kind, context=context)
        if ref is not None:
            safe[output_key] = ref
    doctor_refs = _entity_refs(value.get("doctor_ids"), kind="doctor", context=context)
    if doctor_refs:
        safe["doctor_refs"] = doctor_refs
    for key in ("date", "time", "package_usage"):
        item = value.get(key)
        if item not in (None, "", {}, []):
            safe[key] = item
    return safe


def _safe_target(value: object, context: SemanticContext) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, object] = {}
    appointment_ref = _entity_ref(
        value.get("appointment_id"),
        kind="appointment",
        context=context,
    )
    if appointment_ref is not None:
        safe["appointment_ref"] = appointment_ref
    safe.update(_safe_constraints(value, context))
    if value.get("start_local") not in (None, ""):
        safe["start_local"] = value.get("start_local")
    return safe


def _safe_option_snapshot(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, object] = {}
    purpose = value.get("purpose")
    if purpose not in (None, ""):
        safe["purpose"] = purpose
    raw_options = value.get("options")
    if not isinstance(raw_options, list):
        return safe
    options: list[dict[str, object]] = []
    for index, raw in enumerate(raw_options, start=1):
        if not isinstance(raw, dict):
            continue
        option: dict[str, object] = {"index": index}
        if raw.get("label") not in (None, ""):
            option["label"] = raw.get("label")
        payload = raw.get("payload")
        if isinstance(payload, dict):
            for key in (
                "start_time_24h",
                "end_time_24h",
                "start_local",
                "doctor_name",
                "laser_device_name",
                "service_name",
            ):
                if payload.get(key) not in (None, ""):
                    option[key] = payload.get(key)
        options.append(option)
    if options:
        safe["options"] = options
    return safe


def active_task_semantic_view(
    active_task: dict[str, Any] | None,
    *,
    context: SemanticContext,
) -> dict[str, object]:
    """Expose only ephemeral refs and conversational task facts to the interpreter."""
    if not isinstance(active_task, dict):
        return {}
    task_type = active_task.get("task_type")
    if task_type not in {"booking", "reschedule"}:
        return {}

    safe: dict[str, object] = {"task_type": task_type}
    if active_task.get("status") not in (None, ""):
        safe["status"] = active_task.get("status")

    if task_type == "booking":
        constraints = _safe_constraints(active_task.get("constraints"), context)
        if constraints:
            safe["constraints"] = constraints
    else:
        target = _safe_target(active_task.get("target"), context)
        replacement = _safe_constraints(active_task.get("replacement"), context)
        if target:
            safe["target"] = target
        if replacement:
            safe["replacement"] = replacement

    snapshot = _safe_option_snapshot(active_task.get("option_snapshot"))
    if snapshot:
        safe["pending_choice"] = snapshot
    return safe


def verified_read_semantic_view(
    read_context: dict[str, Any] | None,
    *,
    context: SemanticContext,
) -> dict[str, object]:
    """Expose only the immediately previous verified read scope and safe result summary."""
    if not isinstance(read_context, dict):
        return {}
    operation_type = read_context.get("operation_type")
    if not isinstance(operation_type, str) or not operation_type:
        return {}
    safe: dict[str, object] = {"operation_type": operation_type}
    safe.update(_safe_constraints(read_context, context))
    option_count = read_context.get("availability_option_count")
    if isinstance(option_count, int) and option_count >= 0:
        safe["availability_option_count"] = option_count
        safe["availability_found"] = option_count > 0
    return safe


def pending_choice_semantic_view(value: dict[str, Any] | None) -> dict[str, object]:
    return _safe_option_snapshot(value)


def with_safe_task_context(
    context: SemanticContext,
    *,
    active_task: dict[str, Any] | None = None,
    pending_choice: dict[str, Any] | None = None,
) -> SemanticContext:
    model_input = dict(context.model_input)
    model_input["active_task"] = active_task_semantic_view(active_task, context=context)
    model_input["pending_choice"] = pending_choice_semantic_view(pending_choice)
    return SemanticContext(model_input=model_input, reference_map=context.reference_map)


def with_safe_read_context(
    context: SemanticContext,
    *,
    read_context: dict[str, Any] | None = None,
) -> SemanticContext:
    if read_context is None:
        return context
    model_input = dict(context.model_input)
    model_input["recent_verified_read"] = verified_read_semantic_view(
        read_context,
        context=context,
    )
    return SemanticContext(model_input=model_input, reference_map=context.reference_map)
