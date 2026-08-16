from __future__ import annotations

import hashlib
import secrets


def hash_adapter_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_adapter_token() -> tuple[str, str]:
    token = f"tia_ch_{secrets.token_urlsafe(32)}"
    return token, hash_adapter_token(token)


def channel_to_patient_source(channel: str) -> str:
    if channel == "web":
        return "website"
    if channel in {"whatsapp", "instagram", "facebook", "email"}:
        return channel
    return "other"
