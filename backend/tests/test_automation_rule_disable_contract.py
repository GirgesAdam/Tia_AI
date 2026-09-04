from pathlib import Path


def _route_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "app/api/routes/automations.py").read_text(encoding="utf-8")


def test_disabling_rule_immediately_cancels_safely_queued_provider_sends() -> None:
    source = _route_source()
    update = source.split("def update_rule(", 1)[1].split("@router.get(\"/overview\"", 1)[0]
    assert 'AutomationJob.status.in_(("queued", "failed"))' in update
    assert 'AutomationJob.status == "dispatched"' in update
    assert 'MessageDispatch.status == "queued"' in update
    assert "cancel_automation_job(" in update
    assert "actor_user_id=access.user.id" in update


def test_rule_disable_does_not_claim_processing_or_already_sent_dispatches() -> None:
    source = _route_source()
    update = source.split("def update_rule(", 1)[1].split("@router.get(\"/overview\"", 1)[0]
    assert 'MessageDispatch.status == "processing"' not in update
    assert 'MessageDispatch.status == "sent"' not in update


def test_rule_disable_marks_cancellation_as_lifecycle_renewable_not_manual_job_cancel() -> None:
    source = _route_source()
    update = source.split("def update_rule(", 1)[1].split("@router.get(\"/overview\"", 1)[0]
    assert '"reason": "rule_disabled_by_admin"' in update
