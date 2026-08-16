from types import SimpleNamespace

from app.agents.tools.clinic_tools import (
    _branch_display_address,
    _branch_search_text,
    _normalize_lookup_text,
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
