from pathlib import Path
from types import SimpleNamespace

from app.services.channels import _template_dispatch_is_allowed


def _message(*, message_type: str = "template", name: str | None = "approved_one"):
    metadata = {}
    if name is not None:
        metadata["whatsapp_template"] = {"name": name}
    return SimpleNamespace(message_type=message_type, metadata_json=metadata)


def test_approved_template_is_not_blocked_by_other_pending_templates() -> None:
    approved = frozenset({"approved_one", "approved_followup"})

    assert _template_dispatch_is_allowed(
        _message(name="approved_one"),
        approved_template_names=approved,
    ) is True
    assert _template_dispatch_is_allowed(
        _message(name="still_pending"),
        approved_template_names=approved,
    ) is False


def test_text_dispatch_is_never_blocked_by_template_approval_pool() -> None:
    assert _template_dispatch_is_allowed(
        _message(message_type="text", name=None),
        approved_template_names=frozenset(),
    ) is True


def test_malformed_template_is_claimed_for_deterministic_failure() -> None:
    assert _template_dispatch_is_allowed(
        _message(name=None),
        approved_template_names=frozenset(),
    ) is True


def test_none_approval_pool_preserves_legacy_generic_claim_behavior() -> None:
    assert _template_dispatch_is_allowed(
        _message(name="anything"),
        approved_template_names=None,
    ) is True


def test_native_transport_gates_each_template_individually() -> None:
    root = Path(__file__).resolve().parents[2]
    channels = (root / "backend/app/services/channels.py").read_text(encoding="utf-8")
    transport = (
        root / "backend/app/services/meta_whatsapp_transport.py"
    ).read_text(encoding="utf-8")

    assert "approved_template_names: frozenset[str] | set[str] | None = None" in channels
    assert "dispatch.next_attempt_at = now + timedelta(minutes=2)" in channels
    assert "approved_template_names = frozenset(" in transport
    assert "approved_template_names=approved_template_names" in transport
    assert "allow_templates = not required_templates or all(" not in transport
