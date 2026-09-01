from pathlib import Path


def test_final_gate_does_not_construct_incompatible_client_options() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_final_internal_gate.py").read_text(encoding="utf-8")

    assert "ClientOptions" not in source
    assert "settings.supabase_secret_key" in source
    assert ".auth.admin.create_user(" in source
    assert ".auth.admin.delete_user(" in source
