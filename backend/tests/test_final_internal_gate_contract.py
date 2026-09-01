from pathlib import Path


def test_final_gate_runner_contains_critical_boundaries() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_final_internal_gate.py").read_text(encoding="utf-8")
    required = (
        "TRUE CONCURRENT BOOKING RACE",
        "MULTI-TENANT ISOLATION",
        "REAL MEMBER RBAC",
        "STATEFUL WORKFLOW CONCURRENCY + EXPIRY",
        "AUTOMATION LIFECYCLE",
        "CHANNEL + HANDOFF RACES",
        "FRONTEND E2E",
        "ThreadPoolExecutor",
        "FlowStateConflictError",
        "Late failed callback cannot downgrade read",
        "Paused inbound creates no AI outbound message or dispatch",
    )
    for token in required:
        assert token in source


def test_final_gate_never_embeds_member_password() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_final_internal_gate.py").read_text(encoding="utf-8")
    assert "member_password = secrets.token_urlsafe" in source
    assert "print(member_password" not in source
    assert "Supabase member password:" not in source


def test_final_gate_is_staging_only() -> None:
    backend = Path(__file__).resolve().parent.parent
    for name in (
        "run_final_internal_gate.py",
        "seed_final_internal_gate.py",
        "cleanup_final_internal_gate.py",
    ):
        source = (backend / "scripts" / name).read_text(encoding="utf-8")
        assert "settings.is_production" in source
