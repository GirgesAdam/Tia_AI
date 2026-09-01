from types import SimpleNamespace

from app.core.config import settings
from app.services.channels import _dispatch_has_retry_budget


def test_dispatch_retry_budget_stops_at_configured_cap() -> None:
    assert settings.channel_dispatch_max_attempts >= 1
    below = SimpleNamespace(attempts=settings.channel_dispatch_max_attempts - 1)
    at_cap = SimpleNamespace(attempts=settings.channel_dispatch_max_attempts)

    assert _dispatch_has_retry_budget(below) is True
    assert _dispatch_has_retry_budget(at_cap) is False
