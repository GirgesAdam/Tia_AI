from __future__ import annotations

from collections.abc import Hashable

from app.agents.v2.turn_contract import (
    DateConstraint,
    EntityReference,
    TiaTurnUnderstanding,
    TurnOperation,
)


def _entity_identity(entity: EntityReference | None) -> Hashable:
    if entity is None:
        return None
    if entity.ref is not None:
        return ("ref", entity.ref)
    if entity.candidate_refs:
        return ("candidates", entity.candidate_mode, tuple(entity.candidate_refs))
    return ("ungrounded_text", entity.text)


def _default_read_availability_date(operation: TurnOperation) -> TurnOperation:
    """Make an undated availability read mean the nearest upcoming availability.

    Availability is intrinsically read-only, so this default can improve useful discovery without
    authorizing or approximating any write. Booking/reschedule operations keep their stricter date
    requirements and are intentionally untouched here.
    """
    if operation.type != "availability" or operation.entities.date is not None:
        return operation
    entities = operation.entities.model_copy(
        update={
            "date": DateConstraint(
                mode="next_available",
                start_date=None,
                end_date=None,
            )
        }
    )
    return operation.model_copy(update={"entities": entities})


def _operation_identity(operation: TurnOperation) -> Hashable:
    entities = operation.entities
    return (
        operation.type,
        operation.execution_intent,
        operation.continues_previous,
        _entity_identity(entities.service),
        _entity_identity(entities.doctor),
        _entity_identity(entities.device),
        _entity_identity(entities.appointment),
        _entity_identity(entities.package),
        entities.date.model_dump_json() if entities.date is not None else None,
        entities.time.model_dump_json() if entities.time is not None else None,
        entities.package_sessions,
        entities.marketing_consent,
        entities.follow_up_at_local,
        operation.selection.model_dump_json() if operation.selection is not None else None,
        operation.package_usage,
        tuple(operation.requested_service_details),
    )


def dedupe_exact_operations(turn: TiaTurnUnderstanding) -> TiaTurnUnderstanding:
    """Normalize safe read defaults, then drop exact duplicates in customer order.

    This works only on the structured interpreter contract. It never inspects raw customer text and
    never merges operations whose grounded entities, execution intent, or constraints differ.
    """

    seen: set[Hashable] = set()
    operations: list[TurnOperation] = []
    for raw_operation in turn.operations:
        operation = _default_read_availability_date(raw_operation)
        identity = _operation_identity(operation)
        if identity in seen:
            continue
        seen.add(identity)
        operations.append(operation)

    if operations == turn.operations:
        return turn
    return turn.model_copy(update={"operations": operations})
