from pathlib import Path


def test_post_import_smoke_script_is_read_only_and_covers_runtime_domains() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts" / "run_post_import_smoke.py").read_text(encoding="utf-8")
    lower = source.lower()

    for expected in (
        "history.provenance_links",
        "runtime.patients",
        "runtime.appointment_joins",
        "runtime.payments",
        "runtime.packages",
        "runtime.analytics_overview",
    ):
        assert expected in source

    assert "db.commit(" not in lower
    assert "db.delete(" not in lower
    assert "db.add(" not in lower
    assert "analytics_overview(" in source
    assert "clinicHistoricalImportLink".lower() in lower.replace("_", "")
