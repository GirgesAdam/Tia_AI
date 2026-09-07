from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class ProviderCredentialError(RuntimeError):
    pass


def provider_credential_encryption_ready() -> bool:
    value = settings.channel_credential_encryption_key
    return bool(value and value.strip())


def _fernet() -> Fernet:
    raw = settings.channel_credential_encryption_key
    if not raw or not raw.strip():
        raise ProviderCredentialError(
            "Provider credential encryption is not configured on the Tia platform."
        )
    try:
        return Fernet(raw.strip().encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise ProviderCredentialError(
            "Provider credential encryption key is invalid."
        ) from exc


def encrypt_provider_access_token(token: str) -> str:
    value = token.strip()
    if not value:
        raise ProviderCredentialError("Provider access token cannot be empty.")
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_provider_access_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ProviderCredentialError(
            "Stored provider credential cannot be decrypted with the configured key."
        ) from exc
