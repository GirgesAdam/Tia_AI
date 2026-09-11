from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def test_laser_service_creation_switches_from_base_price_to_device_prices() -> None:
    form = (FRONTEND / "src/app/(dashboard)/services/service-create-form.tsx").read_text(
        encoding="utf-8"
    )
    actions = (FRONTEND / "src/app/(dashboard)/services/actions.ts").read_text(
        encoding="utf-8"
    )
    page = (FRONTEND / "src/app/(dashboard)/services/page.tsx").read_text(
        encoding="utf-8"
    )

    assert "useState(false)" in form
    assert "requiresLaserDevice ? (" in form
    assert 'name="prime_lase_price"' in form
    assert 'name="candela_gentle_price"' in form
    assert 'name="price"' in form
    assert "ServiceCreateForm" in page
    assert "price_minor: requiresLaserDevice ? 0 : basePriceMinor" in actions
    assert 'device_key: "prime_lase"' in actions
    assert 'device_key: "candela_gentle"' in actions
    assert "prime_lase_price" in actions
    assert "candela_gentle_price" in actions
