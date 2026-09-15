from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.models.workspace import Workspace


@dataclass(frozen=True)
class WorkspaceRuntimePolicy:
    is_demo: bool
    allow_external_dispatch: bool
    agent_hourly_turn_limit: int | None


def workspace_runtime_policy(workspace: Workspace) -> WorkspaceRuntimePolicy:
    """Return tenant-scoped runtime capabilities.

    The workspace row is the only business source of truth. Legacy deployment
    DEMO_MODE flags are deliberately ignored so one demo tenant can safely share
    a production runtime with real clinics.
    """
    is_demo = bool(workspace.is_demo)
    return WorkspaceRuntimePolicy(
        is_demo=is_demo,
        allow_external_dispatch=not is_demo,
        agent_hourly_turn_limit=(
            settings.demo_agent_hourly_turn_limit if is_demo else None
        ),
    )
