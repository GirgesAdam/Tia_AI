from __future__ import annotations

import inspect

from app.agents.tools import clinic_tools


def test_availability_display_context_is_kept_for_legacy_and_tests() -> None:
    signature = inspect.signature(clinic_tools._availability_display_context)
    assert "preloaded_branch" in signature.parameters
    assert "preloaded_service" in signature.parameters


def test_availability_payload_uses_adapter_boundary() -> None:
    names = clinic_tools._availability_payload.__code__.co_names
    assert "_adapter_availability" in names
    assert "calculate_availability" not in names
