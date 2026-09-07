from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.channel_adapter import generate_adapter_token
from app.core.meta_whatsapp_config import meta_whatsapp_settings as settings
from app.models.automation_rule import AutomationRule
from app.models.channel_connection import ChannelConnection
from app.models.channel_provider_credential import ChannelProviderCredential
from app.schemas.whatsapp_setup import WhatsAppEmbeddedSignupConfig, WhatsAppSetupState
from app.services.provider_credentials import (
    ProviderCredentialError,
    encrypt_provider_access_token,
    provider_credential_encryption_ready,
)


class MetaWhatsAppSetupError(RuntimeError):
    pass


class MetaWhatsAppConfigurationError(MetaWhatsAppSetupError):
    pass


class MetaWhatsAppConflictError(MetaWhatsAppSetupError):
    pass


class MetaWhatsAppProviderError(MetaWhatsAppSetupError):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def embedded_signup_available() -> bool:
    return all(
        (
            _clean_optional(settings.meta_app_id),
            _clean_optional(settings.meta_app_secret),
            _clean_optional(settings.meta_whatsapp_embedded_signup_config_id),
            _clean_optional(settings.meta_graph_api_version),
            _clean_optional(settings.meta_webhook_verify_token),
            _clean_optional(settings.channel_transport_worker_token),
            provider_credential_encryption_ready(),
        )
    )


def embedded_signup_public_config() -> WhatsAppEmbeddedSignupConfig:
    available = embedded_signup_available()
    return WhatsAppEmbeddedSignupConfig(
        available=available,
        app_id=_clean_optional(settings.meta_app_id) if available else None,
        config_id=(
            _clean_optional(settings.meta_whatsapp_embedded_signup_config_id)
            if available
            else None
        ),
        graph_api_version=(
            _clean_optional(settings.meta_graph_api_version) if available else None
        ),
    )


def _graph_url(path: str) -> str:
    version = _clean_optional(settings.meta_graph_api_version)
    if not version:
        raise MetaWhatsAppConfigurationError(
            "Meta Graph API version is not configured on the Tia platform."
        )
    normalized = version if version.startswith("v") else f"v{version}"
    return f"https://graph.facebook.com/{normalized}/{path.lstrip('/')}"


def _provider_error(response: httpx.Response, fallback: str) -> MetaWhatsAppProviderError:
    code: str | None = None
    message = fallback
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        raw_error = payload.get("error")
        if isinstance(raw_error, dict):
            if raw_error.get("message"):
                message = str(raw_error["message"])
            if raw_error.get("code") is not None:
                code = str(raw_error["code"])
    return MetaWhatsAppProviderError(message, code=code)


def _setup_provider_health(
    provider_error: MetaWhatsAppProviderError | None,
    *,
    now: datetime,
) -> dict[str, Any]:
    code = provider_error.code if provider_error else None
    state = (
        "disabled"
        if code == "131031"
        else "degraded"
        if provider_error is not None
        else "setup_pending"
    )
    health: dict[str, Any] = {
        "state": state,
        "current_error_code": code,
        "current_error": str(provider_error) if provider_error else None,
        "last_checked_at": now.isoformat(),
    }
    if code == "190":
        health["action_required"] = "reconnect_meta"
    elif code == "131031":
        health["action_required"] = "meta_account_review"
    return health


def _exchange_signup_code(code: str) -> tuple[str, datetime | None]:
    app_id = _clean_optional(settings.meta_app_id)
    app_secret = _clean_optional(settings.meta_app_secret)
    if not app_id or not app_secret or not embedded_signup_available():
        raise MetaWhatsAppConfigurationError(
            "WhatsApp Embedded Signup is not configured on the Tia platform."
        )

    try:
        response = httpx.get(
            _graph_url("oauth/access_token"),
            params={
                "client_id": app_id,
                "client_secret": app_secret,
                "code": code,
            },
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise MetaWhatsAppProviderError(
            "Could not reach Meta while completing WhatsApp connection."
        ) from exc
    if response.status_code >= 400:
        raise _provider_error(response, "Meta rejected the Embedded Signup code.")
    payload = response.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise MetaWhatsAppProviderError(
            "Meta completed signup without returning a usable access token."
        )
    expires_at = None
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
    return token, expires_at


def _read_phone_number(token: str, phone_number_id: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            _graph_url(phone_number_id),
            params={"fields": "id,display_phone_number,verified_name,quality_rating"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise MetaWhatsAppProviderError(
            "Could not verify the selected WhatsApp number with Meta."
        ) from exc
    if response.status_code >= 400:
        raise _provider_error(response, "Meta could not verify the selected WhatsApp number.")
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _subscribe_app(token: str, waba_id: str) -> None:
    try:
        response = httpx.post(
            _graph_url(f"{waba_id}/subscribed_apps"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise MetaWhatsAppProviderError(
            "Could not subscribe the clinic WhatsApp account to Tia webhooks."
        ) from exc
    if response.status_code >= 400:
        raise _provider_error(
            response,
            "Meta rejected the WhatsApp webhook subscription for this business account.",
        )


def _template_statuses(connection: ChannelConnection | None) -> dict[str, str]:
    if connection is None:
        return {}
    raw = (connection.config_json or {}).get("template_statuses")
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def build_whatsapp_setup_state(
    db: Session,
    *,
    workspace_id: UUID,
) -> WhatsAppSetupState:
    connection = db.scalar(
        select(ChannelConnection)
        .where(
            ChannelConnection.workspace_id == workspace_id,
            ChannelConnection.channel == "whatsapp",
            ChannelConnection.status != "disconnected",
        )
        .order_by(ChannelConnection.created_at.desc())
        .limit(1)
    )
    config = dict(connection.config_json or {}) if connection is not None else {}
    health_raw = config.get("provider_health")
    health = health_raw if isinstance(health_raw, dict) else {}
    credential = (
        db.get(ChannelProviderCredential, connection.id) if connection is not None else None
    )
    rules = list(
        db.scalars(
            select(AutomationRule).where(
                AutomationRule.workspace_id == workspace_id,
                AutomationRule.enabled.is_(True),
                AutomationRule.channel.in_(("whatsapp", "auto")),
            )
        )
    )
    required_templates = [rule.template_name for rule in rules if rule.template_name]
    statuses = _template_statuses(connection)
    templates_ready = not required_templates or all(
        statuses.get(name, "").lower() == "approved" for name in required_templates
    )
    provider_health_state = (
        str(health.get("state")) if health.get("state") is not None else None
    )
    provider_error_code = (
        str(health.get("current_error_code"))
        if health.get("current_error_code") is not None
        else None
    )
    provider_error = (
        str(health.get("current_error")) if health.get("current_error") else None
    )
    credentials_ready = credential is not None and bool(credential.access_token_ciphertext)
    transport_ready = bool(config.get("transport_ready"))
    connected = connection is not None
    ready = bool(
        connection is not None
        and connection.status == "active"
        and credentials_ready
        and transport_ready
        and templates_ready
        and provider_health_state not in {"disabled", "degraded"}
    )

    admin_action: str = "none"
    admin_message = None
    system_message = None
    if connection is None:
        admin_action = "connect_meta"
        admin_message = (
            "سجّل الدخول إلى Meta واختَر Business العيادة ورقم واتساب. "
            "Tia ستتعامل مع IDs وTokens وإعداد الاتصال تلقائيًا."
        )
    elif str(health.get("action_required") or "") == "reconnect_meta":
        admin_action = "connect_meta"
        admin_message = "جلسة Meta انتهت أو بيانات الربط لم تعد صالحة. أعد ربط واتساب من نفس الزر؛ لن تحتاج لإدخال IDs أو Tokens."
    elif provider_health_state == "disabled" or provider_error_code == "131031":
        admin_action = "resolve_meta_restriction"
        admin_message = (
            "Meta أوقفت أو قيّدت حساب واتساب. افتح Business Support Home ونفّذ المراجعة المطلوبة."
        )
    elif not transport_ready:
        system_message = "Tia بتجهز مسار الإرسال الآمن لهذا الرقم."
    elif not templates_ready:
        rejected_templates = [
            name for name in required_templates if statuses.get(name, "").lower() == "rejected"
        ]
        if rejected_templates:
            admin_action = "wait_for_template_review"
            admin_message = "Meta رفضت قالب رسالة مطلوب للـAutomation. Tia ستعرض القالب المطلوب تعديله أو إعادة مراجعته."
        else:
            system_message = "Tia بتتحقق من القوالب المطلوبة للـAutomations المفعلة."

    return WhatsAppSetupState(
        connection_id=connection.id if connection else None,
        connection_status=connection.status if connection else None,
        connected=connected,
        display_name=connection.display_name if connection else None,
        display_phone_number=(
            str(config.get("display_phone_number"))
            if config.get("display_phone_number")
            else None
        ),
        verified_name=str(config.get("verified_name")) if config.get("verified_name") else None,
        provider_health_state=provider_health_state,
        provider_error_code=provider_error_code,
        provider_error=provider_error,
        embedded_signup_available=embedded_signup_available(),
        provider_credentials_ready=credentials_ready,
        transport_ready=transport_ready,
        templates_ready=templates_ready,
        ready_for_automations=ready,
        admin_action=admin_action,  # type: ignore[arg-type]
        admin_message=admin_message,
        system_message=system_message,
    )


def complete_embedded_signup(
    db: Session,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID,
    code: str,
    waba_id: str,
    phone_number_id: str,
    business_id: str | None,
) -> WhatsAppSetupState:
    token, expires_at = _exchange_signup_code(code)
    try:
        ciphertext = encrypt_provider_access_token(token)
    except ProviderCredentialError as exc:
        raise MetaWhatsAppConfigurationError(str(exc)) from exc

    phone_info: dict[str, Any] = {}
    provider_error: MetaWhatsAppProviderError | None = None
    try:
        phone_info = _read_phone_number(token, phone_number_id)
        _subscribe_app(token, waba_id)
    except MetaWhatsAppProviderError as exc:
        provider_error = exc

    same_connection = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.workspace_id == workspace_id,
            ChannelConnection.channel == "whatsapp",
            ChannelConnection.provider == "meta_cloud",
            ChannelConnection.external_account_id == phone_number_id,
        )
    )
    other_connection = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.workspace_id == workspace_id,
            ChannelConnection.channel == "whatsapp",
            ChannelConnection.status != "disconnected",
            ChannelConnection.external_account_id != phone_number_id,
        )
    )
    if same_connection is None and other_connection is not None:
        raise MetaWhatsAppConflictError(
            "A different WhatsApp number is already connected to this clinic. Disconnect it before replacing the number."
        )

    now = datetime.now(UTC)
    display_phone = str(phone_info.get("display_phone_number") or "").strip() or None
    verified_name = str(phone_info.get("verified_name") or "").strip() or None
    quality_rating = str(phone_info.get("quality_rating") or "").strip() or None
    health = _setup_provider_health(provider_error, now=now)

    if same_connection is None:
        _, adapter_token_hash = generate_adapter_token()
        connection = ChannelConnection(
            workspace_id=workspace_id,
            channel="whatsapp",
            provider="meta_cloud",
            display_name=verified_name or display_phone or "WhatsApp",
            status="paused",
            external_account_id=phone_number_id,
            adapter_token_hash=adapter_token_hash,
            created_by_user_id=created_by_user_id,
            config_json={},
        )
        db.add(connection)
        db.flush()
    else:
        connection = same_connection
        connection.display_name = verified_name or display_phone or connection.display_name
        connection.status = "paused"

    current_config = dict(connection.config_json or {})
    current_config.update(
        {
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "business_id": business_id,
            "display_phone_number": display_phone,
            "verified_name": verified_name,
            "quality_rating": quality_rating,
            "embedded_signup_completed_at": now.isoformat(),
            "transport_ready": False,
            "provider_health": health,
        }
    )
    connection.config_json = current_config

    credential = db.get(ChannelProviderCredential, connection.id)
    if credential is None:
        credential = ChannelProviderCredential(
            channel_connection_id=connection.id,
            workspace_id=workspace_id,
            provider="meta_cloud",
            access_token_ciphertext=ciphertext,
            token_type="bearer",
            expires_at=expires_at,
        )
        db.add(credential)
    else:
        credential.provider = "meta_cloud"
        credential.access_token_ciphertext = ciphertext
        credential.token_type = "bearer"
        credential.expires_at = expires_at

    db.commit()
    db.refresh(connection)
    if provider_error is None:
        from app.services.meta_whatsapp_transport import refresh_meta_connection_readiness

        refresh_meta_connection_readiness(db, connection)
    return build_whatsapp_setup_state(db, workspace_id=workspace_id)
