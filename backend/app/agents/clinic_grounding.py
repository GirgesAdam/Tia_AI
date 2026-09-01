from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from copy import deepcopy
import logging
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.clinic.registry import get_clinic_adapter
from app.integrations.clinic.tia_database import (
    filter_bookable_doctor_rows as _filter_bookable_doctor_rows,
)
from app.models.workspace import Workspace


logger = logging.getLogger(__name__)

_CATALOG_CACHE_MAX_ENTRIES = 128
_catalog_cache_lock = Lock()
_catalog_cache: OrderedDict[UUID, tuple[object, dict[str, Any]]] = OrderedDict()


def _catalog_cache_get(
    workspace_id: UUID,
    signature: object,
) -> dict[str, Any] | None:
    with _catalog_cache_lock:
        cached = _catalog_cache.get(workspace_id)
        if cached is None or cached[0] != signature:
            return None
        _catalog_cache.move_to_end(workspace_id)
        return deepcopy(cached[1])


def _catalog_cache_put(
    workspace_id: UUID,
    signature: object,
    catalog: dict[str, Any],
) -> None:
    with _catalog_cache_lock:
        _catalog_cache[workspace_id] = (signature, deepcopy(catalog))
        _catalog_cache.move_to_end(workspace_id)
        while len(_catalog_cache) > _CATALOG_CACHE_MAX_ENTRIES:
            _catalog_cache.popitem(last=False)


def build_clinic_catalog(db: Session, workspace: Workspace) -> dict[str, Any]:
    """Build/reuse the canonical clinic catalog through the workspace adapter.

    The semantic layer no longer knows how services, branches, doctors, or
    schedules are stored. Tia's native adapter currently reads PostgreSQL; a
    future clinic adapter can provide the same canonical catalog from an API or
    another source system without changing the LLM interpreter.
    """
    adapter = get_clinic_adapter(db=db, workspace=workspace)

    revision_started = perf_counter()
    revision = adapter.catalog_revision()
    revision_ms = int((perf_counter() - revision_started) * 1000)
    cache_signature = (adapter.cache_namespace, revision) if revision is not None else None

    if cache_signature is not None:
        cached = _catalog_cache_get(workspace.id, cache_signature)
        if cached is not None:
            logger.info(
                "Tia clinic catalog workspace_id=%s adapter=%s cache_hit=true revision_ms=%s",
                workspace.id,
                adapter.cache_namespace,
                revision_ms,
            )
            return cached

    build_started = perf_counter()
    catalog = adapter.build_catalog()
    build_ms = int((perf_counter() - build_started) * 1000)

    if cache_signature is not None:
        _catalog_cache_put(workspace.id, cache_signature, catalog)

    logger.info(
        "Tia clinic catalog workspace_id=%s adapter=%s cache_hit=false revision_ms=%s build_ms=%s",
        workspace.id,
        adapter.cache_namespace,
        revision_ms,
        build_ms,
    )
    return deepcopy(catalog)


def _catalog_ids(catalog: dict[str, Any], collection: str) -> set[str]:
    values = catalog.get(collection)
    if not isinstance(values, list):
        return set()
    return {
        str(item.get("id"))
        for item in values
        if isinstance(item, dict) and item.get("id")
    }


def _valid_id(value: str | None, allowed: set[str]) -> str | None:
    if not value:
        return None
    candidate = str(value)
    return candidate if candidate in allowed else None


def _valid_ids(values: Iterable[str] | None, allowed: set[str]) -> list[str]:
    if values is None:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value)
        if candidate in allowed and candidate not in seen:
            result.append(candidate)
            seen.add(candidate)
    return result


def validate_grounded_entity_ids(entity_hints: Any, catalog: dict[str, Any]):
    """Return a copy with only IDs that existed in the supplied catalog snapshot."""
    service_ids = _catalog_ids(catalog, "services")
    branch_ids = _catalog_ids(catalog, "branches")
    doctor_ids = _catalog_ids(catalog, "doctors")

    return entity_hints.model_copy(
        update={
            "service_id": _valid_id(getattr(entity_hints, "service_id", None), service_ids),
            "service_candidate_ids": _valid_ids(
                getattr(entity_hints, "service_candidate_ids", []), service_ids
            ),
            "branch_id": _valid_id(getattr(entity_hints, "branch_id", None), branch_ids),
            "branch_candidate_ids": _valid_ids(
                getattr(entity_hints, "branch_candidate_ids", []), branch_ids
            ),
            "doctor_id": _valid_id(getattr(entity_hints, "doctor_id", None), doctor_ids),
            "doctor_candidate_ids": _valid_ids(
                getattr(entity_hints, "doctor_candidate_ids", []), doctor_ids
            ),
        }
    )


def _rows_for_ids(
    catalog: dict[str, Any],
    collection: str,
    ids: Iterable[str],
) -> list[dict[str, Any]]:
    wanted = list(dict.fromkeys(str(value) for value in ids))
    rank = {value: index for index, value in enumerate(wanted)}
    rows = catalog.get(collection)
    if not isinstance(rows, list):
        return []
    matched = [
        dict(item)
        for item in rows
        if isinstance(item, dict) and str(item.get("id")) in rank
    ]
    matched.sort(key=lambda item: rank[str(item.get("id"))])
    return matched


def grounded_catalog_facts(
    *,
    catalog: dict[str, Any],
    entity_hints: Any,
    capabilities: Iterable[str],
) -> dict[str, Any] | None:
    """Select verified catalog rows using only LLM-returned canonical IDs.

    No customer text is inspected or matched here. The LLM chooses canonical IDs
    from the catalog and
    this function merely materializes those exact PostgreSQL rows.
    """
    capability_set = set(capabilities)
    payload: dict[str, Any] = {
        "ok": True,
        "source": "clinic_adapter_catalog",
    }

    selected_service_id = getattr(entity_hints, "service_id", None)
    service_candidate_ids = list(getattr(entity_hints, "service_candidate_ids", []) or [])
    selected_branch_id = getattr(entity_hints, "branch_id", None)
    branch_candidate_ids = list(getattr(entity_hints, "branch_candidate_ids", []) or [])
    selected_doctor_id = getattr(entity_hints, "doctor_id", None)
    doctor_candidate_ids = list(getattr(entity_hints, "doctor_candidate_ids", []) or [])

    if capability_set.intersection({"service_information", "pricing", "availability_discovery", "appointment_creation"}):
        service_ids = [selected_service_id] if selected_service_id else service_candidate_ids
        if service_ids:
            payload["services"] = _rows_for_ids(catalog, "services", service_ids)
            payload["selected_service_id"] = selected_service_id
            payload["needs_service_choice"] = selected_service_id is None and len(payload["services"]) > 1

    if capability_set.intersection({"branch_discovery", "availability_discovery", "appointment_creation"}):
        branch_ids = [selected_branch_id] if selected_branch_id else branch_candidate_ids
        if branch_ids:
            payload["branches"] = _rows_for_ids(catalog, "branches", branch_ids)
            payload["selected_branch_id"] = selected_branch_id
            payload["needs_branch_choice"] = selected_branch_id is None and len(payload["branches"]) > 1

    if capability_set.intersection({"doctor_discovery", "availability_discovery", "appointment_creation"}):
        doctor_ids = [selected_doctor_id] if selected_doctor_id else doctor_candidate_ids
        if doctor_ids:
            payload["doctors"] = _rows_for_ids(catalog, "doctors", doctor_ids)
            payload["selected_doctor_id"] = selected_doctor_id
            payload["needs_doctor_choice"] = selected_doctor_id is None and len(payload["doctors"]) > 1

    if len(payload) == 2:
        return None
    return payload


def choice_snapshot_from_grounded_facts(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    snapshot: dict[str, Any] = {}
    for flag, collection in (
        ("needs_service_choice", "services"),
        ("needs_branch_choice", "branches"),
        ("needs_doctor_choice", "doctors"),
    ):
        if payload.get(flag) and isinstance(payload.get(collection), list):
            snapshot[flag] = True
            snapshot[collection] = payload[collection]
    return snapshot or None
