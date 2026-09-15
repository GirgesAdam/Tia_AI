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


def _graph_url(path: str) -> str:
    version = (meta_whatsapp_settings.meta_graph_api_version or "").strip()
    if not version:
        raise RuntimeError("Meta Graph API version is not configured.")
    normalized = version if version.startswith("v") else f"v{version}"
    return f"https://graph.facebook.com/{normalized}/{path.lstrip('/')}"


def _error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "unknown"
    raw = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return "unknown"
    return str(raw.get("code") or "unknown")


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
        if waba_id != _EXPECTED_WABA_ID or not verify_token or not app_id:
            print("meta_callback_cutover=FAIL reason=connection_metadata_mismatch")
            return 2

        try:
            token = decrypt_provider_access_token(credential.access_token_ciphertext)
        except ProviderCredentialError:
            print("meta_callback_cutover=FAIL reason=credential_decrypt_failed")
            return 2

        endpoint = _graph_url(f"{waba_id}/subscribed_apps")
        headers = {"Authorization": f"Bearer {token}"}

        # Establish/refresh the app's WABA subscription first. This operation is
        # idempotent for an already-subscribed app and avoids relying on the
        # app-level callback while switching to a WABA-level override.
        try:
            baseline = httpx.post(endpoint, headers=headers, timeout=30.0)
        except httpx.HTTPError:
            print("meta_waba_baseline_subscribe=FAIL reason=meta_post_unreachable")
            return 3
        if baseline.status_code >= 400:
            print(
                "meta_waba_baseline_subscribe=FAIL reason=meta_post_rejected "
                f"status={baseline.status_code} code={_error_code(baseline)}"
            )
            return 3
        print("meta_waba_baseline_subscribe=PASS")

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
            print(
                "meta_callback_cutover=FAIL reason=meta_post_rejected "
                f"status={response.status_code} code={_error_code(response)}"
            )
            return 3
        print("meta_callback_cutover_post=PASS")

        try:
            readback = httpx.get(endpoint, headers=headers, timeout=30.0)
        except httpx.HTTPError:
            print("meta_callback_readback=FAIL reason=meta_get_unreachable")
            return 4
        if readback.status_code >= 400:
            print(
                "meta_callback_readback=FAIL reason=meta_get_rejected "
                f"status={readback.status_code} code={_error_code(readback)}"
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
