from __future__ import annotations

from collections.abc import Hashable

from app.agents.v2.turn_contract import EntityReference, TiaTurnUnderstanding, TurnOperation


def _entity_identity(entity: EntityReference | None) -> Hashable:
    if entity is None:
        return None
    if entity.ref is not None:
        return ("ref", entity.ref)
    if entity.candidate_refs:
        return ("candidates", tuple(entity.candidate_refs))
    return ("ungrounded_text", entity.text)


def _operation_identity(operation: TurnOperation) -> Hashable:
    entities = operation.entities
    return (
        operation.type,
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
    """Drop exact semantic duplicates while preserving the first operation and customer order.

    This works only on the structured interpreter contract. It never inspects raw customer text and
    never merges operations whose grounded entities or constraints differ.
    """

    seen: set[Hashable] = set()
    operations: list[TurnOperation] = []
    for operation in turn.operations:
        identity = _operation_identity(operation)
        if identity in seen:
            continue
        seen.add(identity)
        operations.append(operation)

    if len(operations) == len(turn.operations):
        return turn
    return turn.model_copy(update={"operations": operations})
