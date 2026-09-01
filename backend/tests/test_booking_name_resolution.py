from types import SimpleNamespace

from app.agents.tools.clinic_tools import (
    _branch_display_address,
    _branch_search_text,
    _doctor_search_text,
    _normalize_lookup_text,
    _resolve_doctor_rows_by_search,
    _resolve_services_by_search,
)


def test_branch_name_normalization_keeps_new_cairo_distinct() -> None:
    cairo = SimpleNamespace(
        name="Regression Cairo Branch",
        code="regression-main",
        city="Cairo",
        address_line1="Main address",
        address_line2=None,
    )
    new_cairo = SimpleNamespace(
        name="Regression New Cairo Branch",
        code="regression-new-cairo",
        city="New Cairo",
        address_line1="New Cairo address",
        address_line2=None,
    )

    query = _normalize_lookup_text("Regression Cairo Branch")
    assert query in _branch_search_text(cairo)
    assert query not in _branch_search_text(new_cairo)


def test_branch_display_address_uses_real_model_fields() -> None:
    branch = SimpleNamespace(
        address_line1="Street 1",
        address_line2="Floor 2",
        city="Cairo",
    )
    assert _branch_display_address(branch) == "Street 1، Floor 2، Cairo"


def test_doctor_search_resolves_ai_extracted_name_conservatively() -> None:
    doctor_a = SimpleNamespace(id="a", specialization="Dermatology")
    staff_a = SimpleNamespace(first_name="أحمد", last_name="محمود")
    doctor_b = SimpleNamespace(id="b", specialization="Dermatology")
    staff_b = SimpleNamespace(first_name="أحمد", last_name="سامي")

    assert "احمد محمود" in _doctor_search_text(doctor_a, staff_a)
    matches = _resolve_doctor_rows_by_search(
        [(doctor_a, staff_a), (doctor_b, staff_b)],
        "أحمد محمود",
    )
    assert matches == [(doctor_a, staff_a)]


def test_doctor_search_returns_ambiguous_first_name_instead_of_guessing() -> None:
    doctor_a = SimpleNamespace(id="a", specialization="Dermatology")
    staff_a = SimpleNamespace(first_name="أحمد", last_name="محمود")
    doctor_b = SimpleNamespace(id="b", specialization="Laser")
    staff_b = SimpleNamespace(first_name="أحمد", last_name="سامي")

    matches = _resolve_doctor_rows_by_search(
        [(doctor_a, staff_a), (doctor_b, staff_b)],
        "أحمد",
    )
    assert matches == [(doctor_a, staff_a), (doctor_b, staff_b)]


def test_service_search_prefers_exact_normalized_name_over_longer_variant() -> None:
    exact = SimpleNamespace(name="ليزر إزالة الشعر", category="Laser", description=None)
    demo = SimpleNamespace(name="ليزر إزالة الشعر — Demo", category="Laser", description=None)

    matches = _resolve_services_by_search([exact, demo], "ليزر ازالة الشعر")

    assert matches == [exact]


def test_service_search_keeps_broad_query_ambiguous_when_no_exact_name_exists() -> None:
    first = SimpleNamespace(name="ليزر إزالة الشعر", category="Laser", description=None)
    second = SimpleNamespace(name="ليزر إزالة الشعر — Demo", category="Laser", description=None)

    matches = _resolve_services_by_search([first, second], "ليزر")

    assert matches == [first, second]
