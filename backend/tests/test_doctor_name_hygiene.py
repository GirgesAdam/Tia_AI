from pathlib import Path

from app.core.doctor_names import (
    normalize_doctor_display_name,
    normalize_doctor_name_parts,
    split_doctor_name,
)


def test_doctor_titles_are_presentation_not_stored_identity() -> None:
    assert normalize_doctor_display_name("د. أحمد محمود") == "أحمد محمود"
    assert normalize_doctor_display_name("دكتور أحمد محمود") == "أحمد محمود"
    assert normalize_doctor_display_name("دكتورة سارة علي") == "سارة علي"
    assert normalize_doctor_display_name("Dr. Ahmed Mahmoud") == "Ahmed Mahmoud"
    assert normalize_doctor_display_name("Doctor Ahmed Mahmoud") == "Ahmed Mahmoud"
    assert normalize_doctor_display_name("د.أحمد محمود") == "أحمد محمود"
    assert normalize_doctor_display_name("أ.د. أحمد محمود") == "أحمد محمود"
    assert normalize_doctor_display_name("Prof. Dr. Ahmed Mahmoud") == "Ahmed Mahmoud"


def test_doctor_name_normalization_does_not_transliterate_or_fuzzy_merge() -> None:
    assert normalize_doctor_display_name("Dr. Ahmed Mahmoud") != normalize_doctor_display_name("د. أحمد محمود")


def test_split_doctor_name_removes_title_and_collapses_whitespace() -> None:
    assert split_doctor_name("  د.   أحمد   محمود  ") == ("أحمد", "محمود")
    assert normalize_doctor_name_parts("د.", "مريم حسن") == ("مريم", "حسن")


def test_staging_seed_does_not_store_titles_inside_staff_first_name() -> None:
    root = Path(__file__).resolve().parents[1]
    staging = (root / "scripts/seed_full_staging_demo.py").read_text(encoding="utf-8")
    demo = (root / "scripts/seed_agent_demo.py").read_text(encoding="utf-8")
    realistic = (root / "scripts/seed_realistic_aesthetic_clinic.py").read_text(encoding="utf-8")
    assert 'first_name="د. ' not in staging
    assert 'first_name="دكتور"' not in demo
    assert '"first_name": "د. ' not in realistic
    assert "normalize_doctor_name_parts" in realistic
    assert "assert_unique_active_doctor_names" in realistic


def test_full_regression_seed_isolated_from_primary_tia_workspace() -> None:
    root = Path(__file__).resolve().parents[1]
    scenarios = (root / "scripts/staging_scenarios.py").read_text(encoding="utf-8")
    seed = (root / "scripts/seed_full_staging_demo.py").read_text(encoding="utf-8")
    assert 'REGRESSION_WORKSPACE_SLUG = "tia-regression"' in scenarios
    assert "workspace = db.get(Workspace, REGRESSION_WORKSPACE_ID)" in seed
    assert 'slug=REGRESSION_WORKSPACE_SLUG' in seed
    assert 'primary_workspace = db.scalar(select(Workspace).where(Workspace.slug == "tia"))' in seed


def test_seeded_regression_doctor_names_do_not_include_titles_in_staff_data() -> None:
    root = Path(__file__).resolve().parents[1]
    seed = (root / "scripts/seed_full_staging_demo.py").read_text(encoding="utf-8")
    assert 'first_name="ريجريشن"' in seed
    assert 'first_name="سارة"' in seed
    assert 'first_name="د. ريجريشن"' not in seed
    assert 'first_name="د. سارة"' not in seed


def test_migration_deactivates_only_known_synthetic_doctors_in_primary_demo_workspace() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "alembic/versions/0040_doctor_name_hygiene.py").read_text(encoding="utf-8")
    assert "w.slug = 'tia'" in migration
    assert "%@tia.example" in migration
    assert "%@tia.local" in migration
    assert "SET is_active = FALSE, booking_enabled = FALSE" in migration
    assert "LIKE 'regression-%'" in migration
    assert "LIKE 'demo-%'" in migration
    assert "DELETE FROM doctors" not in migration
