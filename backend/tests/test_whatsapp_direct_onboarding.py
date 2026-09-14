from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.meta_whatsapp_config import meta_whatsapp_settings
from app.core.meta_whatsapp_templates import STANDARD_TEMPLATES_BY_RULE_KEY
from app.schemas.whatsapp_setup import (
    WhatsAppDirectConnect,
    WhatsAppSetupState,
    WhatsAppTemplateSetupStatus,
)
from app.services.meta_whatsapp_onboarding import direct_setup_available
from app.services.provider_credentials import decrypt_provider_secret, encrypt_provider_secret


def _template_states(
    *,
    missing_approved_rule: str | None = None,
    reject_extra_variants: bool = False,
) -> list[WhatsAppTemplateSetupStatus]:
    states: list[WhatsAppTemplateSetupStatus] = []
    for rule_key, templates in STANDARD_TEMPLATES_BY_RULE_KEY.items():
        for index, template in enumerate(templates):
            status = "approved" if index == 0 and rule_key != missing_approved_rule else "pending"
            if reject_extra_variants and index == 1:
                status = "rejected"
            states.append(
                WhatsAppTemplateSetupStatus(
                    rule_key=rule_key,
                    label=template.label_ar,
                    name=template.name,
                    language=template.language,
                    category=template.category,
                    status=status,
                )
            )
    return states


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


def test_setup_is_ready_with_one_approved_template_per_automation() -> None:
    state = WhatsAppSetupState(
        connected=True,
        connection_status="active",
        provider_credentials_ready=True,
        webhook_verified=True,
        transport_ready=True,
        provider_health_state="healthy",
        templates=_template_states(reject_extra_variants=True),
        admin_action="wait_for_template_review",
        admin_message="Old all-variants review gate.",
    )

    assert state.templates_ready is True
    assert state.ready_for_automations is True
    assert state.admin_action == "none"
    assert state.admin_message is None


def test_setup_waits_if_an_automation_has_no_approved_template() -> None:
    state = WhatsAppSetupState(
        connected=True,
        connection_status="active",
        provider_credentials_ready=True,
        webhook_verified=True,
        transport_ready=True,
        provider_health_state="healthy",
        templates=_template_states(missing_approved_rule="post_visit_followup"),
    )

    assert state.templates_ready is False
    assert state.ready_for_automations is False


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


def test_direct_onboarding_uses_stable_meta_entry_links_and_scoped_webhook() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    automation = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")
    route = (backend / "app/api/routes/whatsapp_setup.py").read_text(encoding="utf-8")
    service = (backend / "app/services/meta_whatsapp_onboarding.py").read_text(encoding="utf-8")

    assert "https://developers.facebook.com/apps/" in automation
    assert "https://business.facebook.com/settings/system-users" in automation
    assert "/settings/basic/" in automation
    assert "WhatsApp → API Setup" in automation
    assert "WhatsApp → Configuration" in automation
    assert "use_cases/customize/" not in automation
    assert "1370437594582187" not in automation
    assert "2086664822245784" not in automation
    assert "cleanAppId" in automation
    assert '"/webhook/{connection_id}"' in route
    assert "x-forwarded-proto" in route
    assert "app_secret_ciphertext" in service
    assert '"webhook_verify_token"' in service


def test_direct_onboarding_explains_phone_preparation_and_current_migration_path() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    automation = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")

    assert "طريقة الربط اليدوية الحالية في Tia" in automation
    assert "Tia لا بتنقل ولا بتسجل الرقم بمجرد لصق البيانات" in automation
    assert "WhatsApp Business App" in automation
    assert "WhatsApp Business Platform (Cloud API)" in automation
    assert "لا يستخدم Coexistence" in automation
    assert "Inbox داخل Tia" in automation
    assert "مكالمات الموبايل العادية على الشريحة لا تتأثر" in automation
    assert "Click-to-WhatsApp" in automation


def test_direct_onboarding_keeps_entered_credentials_after_failed_action() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    automation = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")
    actions = (
        repo / "frontend/src/app/(dashboard)/automations/actions.ts"
    ).read_text(encoding="utf-8")

    for state_name in ("appSecret", "wabaId", "phoneNumberId", "accessToken"):
        assert f"const [{state_name}, set" in automation
        assert f"value={{{state_name}}}" in automation
    assert "Meta رفضت التحقق من بيانات الربط" in actions
    assert "technicalMessage" in actions


def test_system_user_link_is_high_contrast_and_right_aligned() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    automation = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")
    assert "!text-teal-700" in automation
    assert 'className="mt-2 w-full text-right"' in automation


def test_pending_template_variants_are_explained_as_non_blocking() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    automation = (
        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"
    ).read_text(encoding="utf-8")
    assert "وجود نسخ إضافية قيد المراجعة مش بيعطل التشغيل" in automation
    assert "Tia تستخدم النسخ المعتمدة فقط" in automation


def test_http_client_info_logging_is_suppressed_for_provider_secret_safety() -> None:
    backend = Path(__file__).resolve().parent.parent
    logging_source = (backend / "app/core/logging.py").read_text(encoding="utf-8")
    assert 'logging.getLogger("httpx").setLevel(logging.WARNING)' in logging_source
    assert 'logging.getLogger("httpcore").setLevel(logging.WARNING)' in logging_source


def test_setup_pending_pause_is_not_rendered_as_provider_failure() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    page = (repo / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")
    assert 'if (healthState === "setup_pending") return false;' in page


def test_whatsapp_setup_has_guided_manual_flow_without_embedded_signup_or_paid_bsp() -> None:
    backend = Path(__file__).resolve().parent.parent
    repo = backend.parent
    automation_page = (
        repo / "frontend/src/app/(dashboard)/automations/page.tsx"
    ).read_text(encoding="utf-8")
    setup_page = (
        repo / "frontend/src/app/(dashboard)/setup/whatsapp/page.tsx"
    ).read_text(encoding="utf-8")

    assert "WhatsAppDirectOnboarding" in automation_page
    assert "WhatsAppDirectOnboarding" in setup_page
    assert "جهّز Meta والرقم مرة واحدة" in setup_page
    assert "خلّي Tia تتحقق وتربط" in setup_page
    assert "فعّل الـWebhook" in setup_page
    assert "Direct Meta Cloud API" not in setup_page
    assert "Meta Cloud API" in setup_page
    assert "من غير مزود وسيط أو اشتراك إضافي لطرف ثالث" in setup_page
    assert "مش محتاج 360dialog أو Twilio أو أي BSP باشتراك شهري" in setup_page
    assert "رسوم WhatsApp/Meta الأصلية" in setup_page
    assert "Meta Embedded Signup غير متاح لنا حاليًا" in setup_page
    assert "لينك يفتح Meta ومعاه اسم المسار" in setup_page
    assert 'href="/automations"' in setup_page
    assert not (repo / "frontend/src/app/(dashboard)/setup/whatsapp/meta-embedded-signup.tsx").exists()
