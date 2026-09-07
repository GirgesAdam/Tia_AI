from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.schemas.whatsapp_setup import WhatsAppEmbeddedSignupComplete
from app.services.meta_whatsapp_onboarding import embedded_signup_public_config
from app.services.provider_credentials import (
    decrypt_provider_access_token,
    encrypt_provider_access_token,
)


def _configure_meta(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setattr(meta_whatsapp_settings, "meta_app_id", "123456")
    monkeypatch.setattr(meta_whatsapp_settings, "meta_app_secret", "super-secret")
    monkeypatch.setattr(
        meta_whatsapp_settings,
        "meta_whatsapp_embedded_signup_config_id",
        "789012",
    )
    monkeypatch.setattr(meta_whatsapp_settings, "meta_graph_api_version", "v25.0")
    monkeypatch.setattr(meta_whatsapp_settings, "meta_webhook_verify_token", "verify-secret")
    monkeypatch.setattr(meta_whatsapp_settings, "channel_transport_worker_token", "worker-secret")
    monkeypatch.setattr(meta_whatsapp_settings, "channel_credential_encryption_key", key)
    return key


def test_provider_access_token_is_encrypted_at_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_meta(monkeypatch)
    token = "EAA-test-provider-token"

    ciphertext = encrypt_provider_access_token(token)

    assert ciphertext != token
    assert token not in ciphertext
    assert decrypt_provider_access_token(ciphertext) == token


def test_embedded_signup_public_config_never_exposes_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_meta(monkeypatch)

    payload = embedded_signup_public_config().model_dump()

    assert payload == {
        "available": True,
        "app_id": "123456",
        "config_id": "789012",
        "graph_api_version": "v25.0",
    }
    assert "secret" not in payload
    assert "token" not in payload
    assert "encryption" not in payload


def test_embedded_signup_is_unavailable_until_tia_platform_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_meta(monkeypatch)
    monkeypatch.setattr(meta_whatsapp_settings, "meta_app_secret", None)

    payload = embedded_signup_public_config()

    assert payload.available is False
    assert payload.app_id is None
    assert payload.config_id is None
    assert payload.graph_api_version is None


def test_embedded_signup_rejects_non_meta_identifiers() -> None:
    with pytest.raises(ValidationError):
        WhatsAppEmbeddedSignupComplete(
            code="valid-code-value",
            waba_id="waba-123",
            phone_number_id="456",
        )


def test_signup_keeps_connection_paused_until_tia_finishes_provisioning() -> None:
    backend = Path(__file__).resolve().parent.parent
    service = (backend / "app/services/meta_whatsapp_onboarding.py").read_text(
        encoding="utf-8"
    )

    assert 'provider="meta_cloud"' in service
    assert 'status="paused"' in service
    assert '"transport_ready": False' in service
    assert "access_token_ciphertext=ciphertext" in service
    assert '"access_token":' not in service


def test_provider_credential_table_is_not_exposed_to_anon_or_authenticated() -> None:
    backend = Path(__file__).resolve().parent.parent
    migration = (
        backend / "alembic/versions/0059_channel_provider_credentials.py"
    ).read_text(encoding="utf-8")

    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL" in migration
    assert '"channel_provider_credentials"' in migration
