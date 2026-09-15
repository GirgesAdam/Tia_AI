from __future__ import annotations

import sys
from uuid import UUID

import httpx

from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.database.session import SessionLocal
from app.models.channel_connection import ChannelConnection
from app.models.channel_provider_credential import ChannelProviderCredential
from app.services.provider_credentials import ProviderCredentialError, decrypt_provider_access_token

_CONNECTION_ID = UUID("5f1d9345-4209-4187-b980-9189f5d84001")
_EXPECTED_WABA_ID = "1088607350781750"
_TARGET_CALLBACK_URL = (
    "https://tia-api-production-54c5.up.railway.app"
    "/api/v1/channels/whatsapp/webhook/5f1d9345-4209-4187-b980-9189f5d84001"
)
_VERIFY_CHALLENGE = "tia-meta-cutover-probe"


def _graph_url(path: str) -> str:
    version = (meta_whatsapp_settings.meta_graph_api_version or "").strip()
    if not version:
        raise RuntimeError("Meta Graph API version is not configured.")
    normalized = version if version.startswith("v") else f"v{version}"
    return f"https://graph.facebook.com/{normalized}/{path.lstrip('/')}"


def _error_details(response: httpx.Response, *secrets: str) -> tuple[str, str, str]:
    try:
        payload = response.json()
    except ValueError:
        return "unknown", "unknown", "unknown"
    raw = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return "unknown", "unknown", "unknown"
    message = str(raw.get("message") or "unknown").replace("\n", " ")
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    return (
        str(raw.get("code") or "unknown"),
        str(raw.get("error_subcode") or "unknown"),
        message[:500],
    )


def _subscription_app_ids(response: httpx.Response) -> list[str]:
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    result: list[str] = []
    if not isinstance(data, list):
        return result
    for item in data:
        if not isinstance(item, dict):
            continue
        app = item.get("whatsapp_business_api_data")
        app_id = str(app.get("id") or "").strip() if isinstance(app, dict) else ""
        if app_id:
            result.append(app_id)
    return result


def _app_whatsapp_subscription(response: httpx.Response) -> tuple[str | None, list[str]]:
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return None, []
    for item in data:
        if not isinstance(item, dict) or item.get("object") != "whatsapp_business_account":
            continue
        callback = str(item.get("callback_url") or "").strip() or None
        fields = item.get("fields")
        names: list[str] = []
        if isinstance(fields, list):
            for field in fields:
                if isinstance(field, str):
                    name = field.strip()
                elif isinstance(field, dict):
                    name = str(field.get("name") or "").strip()
                else:
                    name = ""
                if name:
                    names.append(name)
        return callback, names
    return None, []


def main() -> int:
    with SessionLocal() as db:
        connection = db.get(ChannelConnection, _CONNECTION_ID)
        credential = db.get(ChannelProviderCredential, _CONNECTION_ID)
        if connection is None or credential is None:
            print("meta_callback_cutover=FAIL reason=connection_or_credential_missing")
            return 2

        config = dict(connection.config_json or {})
        waba_id = str(config.get("waba_id") or "").strip()
        verify_token = str(config.get("webhook_verify_token") or "").strip()
        app_id = str(config.get("meta_app_id") or "").strip()
        app_secret = str(config.get("meta_app_secret") or "").strip()
        legacy_callback_url = str(config.get("webhook_callback_url") or "").strip()
        if (
            waba_id != _EXPECTED_WABA_ID
            or not verify_token
            or not app_id
            or not app_secret
            or not legacy_callback_url
        ):
            print("meta_callback_cutover=FAIL reason=connection_metadata_mismatch")
            return 2

        try:
            token = decrypt_provider_access_token(credential.access_token_ciphertext)
        except ProviderCredentialError:
            print("meta_callback_cutover=FAIL reason=credential_decrypt_failed")
            return 2

        headers = {"Authorization": f"Bearer {token}"}
        app_access_token = f"{app_id}|{app_secret}"
        redactions = (token, verify_token, app_secret, app_access_token)

        try:
            verification = httpx.get(
                _TARGET_CALLBACK_URL,
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": verify_token,
                    "hub.challenge": _VERIFY_CHALLENGE,
                },
                timeout=30.0,
            )
        except httpx.HTTPError:
            print("canonical_webhook_verification=FAIL reason=callback_unreachable")
            return 3
        if verification.status_code != 200 or verification.text.strip() != _VERIFY_CHALLENGE:
            print(
                "canonical_webhook_verification=FAIL "
                f"status={verification.status_code} challenge_match={verification.text.strip() == _VERIFY_CHALLENGE}"
            )
            return 3
        print("canonical_webhook_verification=PASS")

        try:
            token_app_response = httpx.get(_graph_url("app"), headers=headers, timeout=30.0)
        except httpx.HTTPError:
            print("meta_token_app_readback=FAIL reason=meta_get_unreachable")
            return 3
        if token_app_response.status_code >= 400:
            code, subcode, message = _error_details(token_app_response, *redactions)
            print(
                "meta_token_app_readback=FAIL reason=meta_get_rejected "
                f"status={token_app_response.status_code} code={code} subcode={subcode} message={message}"
            )
            return 3
        token_app_payload = token_app_response.json()
        token_app_id = str(token_app_payload.get("id") or "").strip() if isinstance(token_app_payload, dict) else ""
        print(f"meta_token_app_readback=PASS app_id={token_app_id or 'unknown'} matches_config={token_app_id == app_id}")
        if token_app_id != app_id:
            print("meta_callback_cutover=FAIL reason=token_app_mismatch")
            return 3

        app_subscriptions_endpoint = _graph_url(f"{app_id}/subscriptions")

        def read_app_subscription() -> tuple[str | None, list[str]] | None:
            try:
                response = httpx.get(
                    app_subscriptions_endpoint,
                    params={"access_token": app_access_token},
                    timeout=30.0,
                )
            except httpx.HTTPError:
                print("meta_app_subscription_readback=FAIL reason=meta_get_unreachable")
                return None
            if response.status_code >= 400:
                code, subcode, message = _error_details(response, *redactions)
                print(
                    "meta_app_subscription_readback=FAIL reason=meta_get_rejected "
                    f"status={response.status_code} code={code} subcode={subcode} message={message}"
                )
                return None
            return _app_whatsapp_subscription(response)

        app_subscription = read_app_subscription()
        if app_subscription is None:
            return 3
        app_callback, app_fields = app_subscription
        print(
            "meta_app_subscription_readback=PASS "
            f"whatsapp_object_present={bool(app_callback or app_fields)} "
            f"whatsapp_messages_subscribed={'messages' in app_fields} "
            f"callback_matches_legacy={app_callback == legacy_callback_url}"
        )

        if "messages" not in app_fields:
            if app_callback and app_callback not in {legacy_callback_url, _TARGET_CALLBACK_URL}:
                print("meta_app_messages_subscribe=FAIL reason=unexpected_existing_callback")
                return 3
            callback_for_app = app_callback or legacy_callback_url
            preserved_fields = sorted(set(app_fields) | {"messages"})
            try:
                app_update = httpx.post(
                    app_subscriptions_endpoint,
                    data={
                        "object": "whatsapp_business_account",
                        "callback_url": callback_for_app,
                        "verify_token": verify_token,
                        "fields": ",".join(preserved_fields),
                        "access_token": app_access_token,
                    },
                    timeout=30.0,
                )
            except httpx.HTTPError:
                print("meta_app_messages_subscribe=FAIL reason=meta_post_unreachable")
                return 3
            if app_update.status_code >= 400:
                code, subcode, message = _error_details(app_update, *redactions)
                print(
                    "meta_app_messages_subscribe=FAIL reason=meta_post_rejected "
                    f"status={app_update.status_code} code={code} subcode={subcode} message={message}"
                )
                return 3
            print("meta_app_messages_subscribe=PASS")
            app_subscription = read_app_subscription()
            if app_subscription is None:
                return 3
            app_callback, app_fields = app_subscription
            if "messages" not in app_fields:
                print("meta_app_messages_readback=FAIL reason=messages_not_confirmed")
                return 3
            print(
                "meta_app_messages_readback=PASS "
                f"callback_matches_legacy={app_callback == legacy_callback_url}"
            )

        endpoint = _graph_url(f"{waba_id}/subscribed_apps")
        try:
            baseline = httpx.post(endpoint, headers=headers, timeout=30.0)
        except httpx.HTTPError:
            print("meta_waba_subscribe=FAIL reason=meta_post_unreachable")
            return 3
        if baseline.status_code >= 400:
            code, subcode, message = _error_details(baseline, *redactions)
            print(
                "meta_waba_subscribe=FAIL reason=meta_post_rejected "
                f"status={baseline.status_code} code={code} subcode={subcode} message={message}"
            )
            return 3
        print("meta_waba_subscribe=PASS")

        try:
            baseline_readback = httpx.get(endpoint, headers=headers, timeout=30.0)
        except httpx.HTTPError:
            print("meta_waba_subscription_readback=FAIL reason=meta_get_unreachable")
            return 3
        if baseline_readback.status_code >= 400:
            code, subcode, message = _error_details(baseline_readback, *redactions)
            print(
                "meta_waba_subscription_readback=FAIL reason=meta_get_rejected "
                f"status={baseline_readback.status_code} code={code} subcode={subcode} message={message}"
            )
            return 3
        subscribed_app_ids = _subscription_app_ids(baseline_readback)
        print(
            "meta_waba_subscription_readback=PASS "
            f"target_app_present={app_id in subscribed_app_ids} "
            f"subscribed_app_ids={','.join(subscribed_app_ids) or 'none'}"
        )

        try:
            response = httpx.post(
                endpoint,
                headers=headers,
                json={
                    "override_callback_uri": _TARGET_CALLBACK_URL,
                    "verify_token": verify_token,
                },
                timeout=30.0,
            )
        except httpx.HTTPError:
            print("meta_callback_cutover=FAIL reason=meta_post_unreachable")
            return 3
        if response.status_code >= 400:
            code, subcode, message = _error_details(response, *redactions)
            print(
                "meta_callback_cutover=FAIL reason=meta_post_rejected "
                f"status={response.status_code} code={code} subcode={subcode} message={message}"
            )
            return 3
        print("meta_callback_cutover_post=PASS")

        try:
            readback = httpx.get(endpoint, headers=headers, timeout=30.0)
        except httpx.HTTPError:
            print("meta_callback_readback=FAIL reason=meta_get_unreachable")
            return 4
        if readback.status_code >= 400:
            code, subcode, message = _error_details(readback, *redactions)
            print(
                "meta_callback_readback=FAIL reason=meta_get_rejected "
                f"status={readback.status_code} code={code} subcode={subcode} message={message}"
            )
            return 4

        payload = readback.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        callback = None
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                app = item.get("whatsapp_business_api_data")
                item_app_id = str(app.get("id") or "") if isinstance(app, dict) else ""
                if item_app_id == app_id:
                    callback = str(item.get("override_callback_uri") or "").strip() or None
                    break

        if callback != _TARGET_CALLBACK_URL:
            print("meta_callback_readback=FAIL reason=canonical_callback_not_confirmed")
            return 4
        print(f"meta_callback_readback=PASS callback={callback}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
