from __future__ import annotations

from collections import OrderedDict
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent_knowledge import (
    KnowledgeEditAction,
    KnowledgeEditDecision,
    KnowledgeEditField,
    KnowledgeEditKind,
    KnowledgeFieldChange,
    KnowledgeScheduleInterval,
)


class KnowledgeEditTransportError(RuntimeError):
    pass


class _FlatKnowledgeEditOperation(BaseModel):
    """Gemini-facing edit operation with a deliberately simple schema.

    The provider gets only strings / enums / string arrays. Empty strings mean
    "not applicable". Python converts the extracted value to the canonical
    type and validates all refs after the model returns.
    """

    kind: KnowledgeEditKind
    target_ref: str = ""
    branch_ref: str = ""
    field: str = ""
    value_type: str = "none"
    value: str = ""
    related_refs: list[str] = Field(default_factory=list)
    primary_branch_ref: str = ""
    weekday: str = ""
    start_time: str = ""
    end_time: str = ""


class _FlatKnowledgeEditDecision(BaseModel):
    understood: bool
    needs_clarification: bool
    clarification_question: str = ""
    assistant_message: str = ""
    operations: list[_FlatKnowledgeEditOperation] = Field(default_factory=list)


def _transport_catalog(catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Replace UUIDs with short request-local refs before the catalog reaches Gemini."""

    ref_to_id: dict[str, str] = {}
    service_id_to_ref: dict[str, str] = {}
    branch_id_to_ref: dict[str, str] = {}
    doctor_id_to_ref: dict[str, str] = {}

    services: list[dict[str, Any]] = []
    for index, row in enumerate(catalog.get("services") or []):
        ref = f"service:{index}"
        source_id = str(row.get("id") or "")
        ref_to_id[ref] = source_id
        service_id_to_ref[source_id] = ref
        services.append({
            "ref": ref,
            "name": row.get("name"),
            "category": row.get("category"),
            "duration_minutes": row.get("duration_minutes"),
            "price_egp": row.get("price_egp"),
            "active": row.get("active"),
        })

    branches: list[dict[str, Any]] = []
    for index, row in enumerate(catalog.get("branches") or []):
        ref = f"branch:{index}"
        source_id = str(row.get("id") or "")
        ref_to_id[ref] = source_id
        branch_id_to_ref[source_id] = ref
        branches.append({
            "ref": ref,
            "name": row.get("name"),
            "city": row.get("city"),
            "address": row.get("address"),
            "timezone": row.get("timezone"),
            "active": row.get("active"),
            "working_hours": row.get("working_hours") or [],
        })

    doctors_source = list(catalog.get("doctors") or [])
    for index, row in enumerate(doctors_source):
        ref = f"doctor:{index}"
        source_id = str(row.get("id") or "")
        ref_to_id[ref] = source_id
        doctor_id_to_ref[source_id] = ref

    doctors: list[dict[str, Any]] = []
    for index, row in enumerate(doctors_source):
        ref = f"doctor:{index}"
        doctors.append({
            "ref": ref,
            "name": row.get("name"),
            "specialization": row.get("specialization"),
            "phone": row.get("phone"),
            "email": row.get("email"),
            "booking_enabled": row.get("booking_enabled"),
            "active": row.get("active"),
            "branches": [
                {
                    "ref": branch_id_to_ref.get(str(item.get("id") or "")),
                    "name": item.get("name"),
                    "primary": item.get("primary"),
                }
                for item in row.get("branches") or []
            ],
            "services": [
                {
                    "ref": service_id_to_ref.get(str(item.get("id") or "")),
                    "name": item.get("name"),
                }
                for item in row.get("services") or []
            ],
            "schedules": [
                {
                    "branch_ref": branch_id_to_ref.get(str(item.get("branch_id") or "")),
                    "branch_name": item.get("branch_name"),
                    "working_hours": item.get("working_hours") or [],
                }
                for item in row.get("schedules") or []
            ],
        })

    return (
        {
            "workspace": catalog.get("workspace") or {},
            "services": services,
            "branches": branches,
            "doctors": doctors,
            "booking_settings": catalog.get("booking_settings"),
        },
        ref_to_id,
    )


def _require_ref(ref: str | None, prefix: str, ref_to_id: dict[str, str]) -> str:
    value = str(ref or "").strip()
    if not value.startswith(prefix + ":") or value not in ref_to_id or not ref_to_id[value]:
        raise KnowledgeEditTransportError(f"Knowledge edit returned an invalid {prefix} catalog reference.")
    return ref_to_id[value]


def _field_change(operation: _FlatKnowledgeEditOperation) -> KnowledgeFieldChange:
    field = str(operation.field or "").strip()
    if not field:
        raise KnowledgeEditTransportError("Knowledge edit field operation omitted the field name.")

    value_type = str(operation.value_type or "").strip().casefold()
    raw_value = str(operation.value or "").strip()
    if value_type == "text":
        return KnowledgeFieldChange(field=field, text_value=raw_value)
    if value_type == "number":
        try:
            number_value = float(raw_value)
        except ValueError as exc:
            raise KnowledgeEditTransportError("Knowledge edit returned a non-numeric numeric value.") from exc
        return KnowledgeFieldChange(field=field, number_value=number_value)
    if value_type == "boolean":
        normalized = raw_value.casefold()
        if normalized in {"true", "1", "yes"}:
            bool_value = True
        elif normalized in {"false", "0", "no"}:
            bool_value = False
        else:
            raise KnowledgeEditTransportError("Knowledge edit returned an invalid boolean value.")
        return KnowledgeFieldChange(field=field, bool_value=bool_value)
    raise KnowledgeEditTransportError("Knowledge edit field operation omitted a supported value_type.")


def _normalize_flat_decision(
    decision: _FlatKnowledgeEditDecision,
    *,
    ref_to_id: dict[str, str],
) -> KnowledgeEditDecision:
    if decision.needs_clarification or not decision.understood:
        return KnowledgeEditDecision(
            understood=decision.understood,
            needs_clarification=True,
            clarification_question=decision.clarification_question or decision.assistant_message,
            assistant_message=decision.assistant_message,
            actions=[],
        )

    field_groups: "OrderedDict[tuple[str, str | None, str | None], list[KnowledgeFieldChange]]" = OrderedDict()
    schedule_groups: "OrderedDict[tuple[str, str, str | None], list[KnowledgeScheduleInterval]]" = OrderedDict()
    relationship_actions: "OrderedDict[tuple[str, str], KnowledgeEditAction]" = OrderedDict()

    for operation in decision.operations:
        kind = operation.kind

        if kind == "update_service":
            entity_id = _require_ref(operation.target_ref, "service", ref_to_id)
            key = (kind, entity_id, None)
            field_groups.setdefault(key, []).append(_field_change(operation))
        elif kind == "update_branch":
            entity_id = _require_ref(operation.target_ref, "branch", ref_to_id)
            key = (kind, entity_id, None)
            field_groups.setdefault(key, []).append(_field_change(operation))
        elif kind == "update_doctor":
            entity_id = _require_ref(operation.target_ref, "doctor", ref_to_id)
            key = (kind, entity_id, None)
            field_groups.setdefault(key, []).append(_field_change(operation))
        elif kind == "update_booking_settings":
            key = (kind, None, None)
            field_groups.setdefault(key, []).append(_field_change(operation))
        elif kind == "set_branch_hours":
            entity_id = _require_ref(operation.target_ref, "branch", ref_to_id)
            if not str(operation.weekday).strip() or not operation.start_time or not operation.end_time:
                raise KnowledgeEditTransportError("Branch-hours operation omitted weekday/start/end.")
            key = (kind, entity_id, None)
            schedule_groups.setdefault(key, []).append(
                KnowledgeScheduleInterval(
                    weekday=int(operation.weekday),
                    start_time=operation.start_time,
                    end_time=operation.end_time,
                )
            )
        elif kind == "set_doctor_hours":
            entity_id = _require_ref(operation.target_ref, "doctor", ref_to_id)
            branch_id = _require_ref(operation.branch_ref, "branch", ref_to_id)
            if not str(operation.weekday).strip() or not operation.start_time or not operation.end_time:
                raise KnowledgeEditTransportError("Doctor-hours operation omitted weekday/start/end.")
            key = (kind, entity_id, branch_id)
            schedule_groups.setdefault(key, []).append(
                KnowledgeScheduleInterval(
                    weekday=int(operation.weekday),
                    start_time=operation.start_time,
                    end_time=operation.end_time,
                )
            )
        elif kind == "set_doctor_services":
            entity_id = _require_ref(operation.target_ref, "doctor", ref_to_id)
            related_ids = [_require_ref(ref, "service", ref_to_id) for ref in operation.related_refs]
            key = (kind, entity_id)
            candidate = KnowledgeEditAction(kind=kind, entity_id=entity_id, related_ids=related_ids)
            existing = relationship_actions.get(key)
            if existing is not None and existing != candidate:
                raise KnowledgeEditTransportError("Knowledge edit returned conflicting doctor-service sets.")
            relationship_actions[key] = candidate
        elif kind == "set_doctor_branches":
            entity_id = _require_ref(operation.target_ref, "doctor", ref_to_id)
            related_ids = [_require_ref(ref, "branch", ref_to_id) for ref in operation.related_refs]
            primary_branch_id = (
                _require_ref(operation.primary_branch_ref, "branch", ref_to_id)
                if operation.primary_branch_ref
                else None
            )
            key = (kind, entity_id)
            candidate = KnowledgeEditAction(
                kind=kind,
                entity_id=entity_id,
                related_ids=related_ids,
                primary_branch_id=primary_branch_id,
            )
            existing = relationship_actions.get(key)
            if existing is not None and existing != candidate:
                raise KnowledgeEditTransportError("Knowledge edit returned conflicting doctor-branch sets.")
            relationship_actions[key] = candidate
        else:  # pragma: no cover - Literal/Pydantic should reject this first.
            raise KnowledgeEditTransportError("Unsupported knowledge edit operation kind.")

    actions: list[KnowledgeEditAction] = []
    for (kind, entity_id, branch_id), changes in field_groups.items():
        # A single natural-language request can change multiple fields on the same
        # entity. Keep it as one canonical action for one confirmation card.
        deduped: OrderedDict[str, KnowledgeFieldChange] = OrderedDict()
        for change in changes:
            existing = deduped.get(change.field)
            if existing is not None and existing != change:
                raise KnowledgeEditTransportError("Knowledge edit returned conflicting values for the same field.")
            deduped[change.field] = change
        actions.append(
            KnowledgeEditAction(
                kind=kind,
                entity_id=entity_id,
                branch_id=branch_id,
                changes=list(deduped.values()),
            )
        )

    for (kind, entity_id, branch_id), schedule in schedule_groups.items():
        actions.append(
            KnowledgeEditAction(
                kind=kind,
                entity_id=entity_id,
                branch_id=branch_id,
                schedule=schedule,
            )
        )

    actions.extend(relationship_actions.values())

    if not actions:
        return KnowledgeEditDecision(
            understood=False,
            needs_clarification=True,
            clarification_question=decision.clarification_question or "ممكن توضح التعديل اللي عايز تعمله؟",
            assistant_message=decision.assistant_message,
            actions=[],
        )

    return KnowledgeEditDecision(
        understood=True,
        needs_clarification=False,
        clarification_question=None,
        assistant_message=decision.assistant_message,
        actions=actions,
    )

