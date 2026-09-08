from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.schemas.whatsapp_setup import WhatsAppDirectConnect
from app.services.meta_whatsapp_onboarding import direct_setup_available
from app.services.provider_credentials import decrypt_provider_secret, encrypt_provider_secret


def test_direct_connect_schema_rejects_non_numeric_meta_ids() -> None:
    with pytest.raises(ValidationError):
        WhatsAppDirectConnect(
            app_id="app-123",
            waba_id="123",
            phone_number_id="456",
            access_token="EAA-test-token-long-enough",
            app_secret="secret-value",
        )


def test_provider_app_secret_is_encrypted_at_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setattr(meta_whatsapp_settings, "channel_credential_encryption_key", key)
    secret = "clinic-meta-app-secret"
    ciphertext = encrypt_provider_secret(secret)
    assert ciphertext != secret
    assert secret not in ciphertext
    assert decrypt_provider_secret(ciphertext) == secret


def test_direct_setup_only_needs_platform_graph_and_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setattr(meta_whatsapp_settings, "meta_graph_api_version", "v26.0")
    monkeypatch.setattr(meta_whatsapp_settings, "channel_credential_encryption_key", key)
    assert direct_setup_available() is True


def test_embedded_signup_is_removed_from_product_routes_and_ui() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    route = (backend / "app/api/routes/whatsapp_setup.py").read_text(encoding="utf-8")
    schema = (backend / "app/schemas/whatsapp_setup.py").read_text(encoding="utf-8")
    automation = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")
    assert "embedded-signup" not in route
    assert "EmbeddedSignup" not in schema
    assert "Embedded Signup" not in automation
    assert "/setup/direct" in route


def test_direct_onboarding_has_meta_deep_links_and_scoped_webhook() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    automation = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")
    route = (backend / "app/api/routes/whatsapp_setup.py").read_text(encoding="utf-8")
    service = (backend / "app/services/meta_whatsapp_onboarding.py").read_text(encoding="utf-8")
    assert "https://developers.facebook.com/apps/" in automation
    assert "https://business.facebook.com/settings/system-users" in automation
    assert "https://business.facebook.com/wa/manage/phone-numbers/" in automation
    assert "whatsapp-business/wa-dev-console/" in automation
    assert "whatsapp-business/wa-settings/" in automation
    assert '"/webhook/{connection_id}"' in route
    assert "app_secret_ciphertext" in service
    assert '"webhook_verify_token"' in service


def test_automation_page_owns_whatsapp_onboarding() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    page = (repo / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")
    setup_redirect = (repo / "frontend/src/app/(dashboard)/setup/whatsapp/page.tsx").read_text(encoding="utf-8")
    assert "WhatsAppDirectOnboarding" in page
    assert 'redirect("/automations")' in setup_redirect
    assert not (repo / "frontend/src/app/(dashboard)/setup/whatsapp/meta-embedded-signup.tsx").exists()
