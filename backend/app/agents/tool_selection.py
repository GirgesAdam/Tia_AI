"""Deprecated compatibility module.

Tia v0.14.0 routes semantic capabilities and maps them to tools through
`capability_policy.py`. No lexical/keyword intent routing lives here.
"""

from app.agents.capability_policy import resolve_capability_policy

__all__ = ["resolve_capability_policy"]
