from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Move WhatsApp onboarding into Automation.
replace(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    'import {\n  cancelAutomationJob,\n  retryAutomationJob,\n  resumeWhatsappConnection,\n  saveAiFollowupTemplates,\n  toggleAutomation,\n} from "./actions";\n',
    'import {\n  cancelAutomationJob,\n  retryAutomationJob,\n  resumeWhatsappConnection,\n  saveAiFollowupTemplates,\n  toggleAutomation,\n} from "./actions";\nimport { WhatsAppDirectOnboarding, type WhatsAppSetupState } from "./whatsapp-direct-onboarding";\n',
)
replace(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    '''export default async function AutomationsPage() {\n  const [rawRules, jobs, overview, connections, ctx] = await Promise.all([\n    tiaRequest<AutomationRule[]>("/automations/rules"),\n    tiaRequest<AutomationJob[]>("/automations/jobs?limit=50"),\n    tiaRequest<AutomationOperationsOverview>("/automations/overview"),\n    tiaRequest<ChannelConnection[]>("/channels/connections"),\n    getAppContext(),\n  ]);\n''',
    '''export default async function AutomationsPage() {\n  const ctx = await getAppContext();\n  const [rawRules, jobs, overview, connections, whatsappSetup] = await Promise.all([\n    tiaRequest<AutomationRule[]>("/automations/rules"),\n    tiaRequest<AutomationJob[]>("/automations/jobs?limit=50"),\n    tiaRequest<AutomationOperationsOverview>("/automations/overview"),\n    tiaRequest<ChannelConnection[]>("/channels/connections"),\n    ctx.workspace.role === "admin"\n      ? tiaRequest<WhatsAppSetupState>("/channels/whatsapp/setup")\n      : Promise.resolve(null),\n  ]);\n''',
)
replace(
    "frontend/src/app/(dashboard)/automations/page.tsx",
    '''      <PageHeader\n        title="Automation"\n        description="فعّل المتابعات التي تحتاجها العيادة وحدد توقيتها بدون إعداد workflows معقدة."\n      />\n\n''',
    '''      <PageHeader\n        title="Automation"\n        description="فعّل المتابعات التي تحتاجها العيادة وحدد توقيتها، واربط واتساب مع Meta من نفس الصفحة."\n      />\n\n      {ctx.workspace.role === "admin" && whatsappSetup && (\n        <Card className="mb-6 border-teal-200">\n          <CardHeader>\n            <CardTitle>تشغيل WhatsApp Automation</CardTitle>\n            <p className="text-sm leading-6 text-[var(--muted)]">\n              إعداد مرة واحدة. كل خطوة فيها لينك مباشر لصفحة Meta المطلوبة، وTia تتحقق من البيانات وتخزن الأسرار مشفرة.\n            </p>\n          </CardHeader>\n          <CardContent>\n            <WhatsAppDirectOnboarding state={whatsappSetup} />\n          </CardContent>\n        </Card>\n      )}\n\n''',
)

# Setup now points admins to Automation instead of maintaining a second WhatsApp setup surface.
replace(
    "frontend/src/app/(dashboard)/setup/page.tsx",
    'اربط رقم العيادة وتابع جاهزية Meta والقوالب ومحرك التنفيذ من مكان واحد، بدون التعامل مع IDs أو Tokens أو n8n.',
    'اربط واتساب من صفحة Automation عبر خطوات Meta الموجهة، وبعدها Tia تتولى التحقق والتشفير والقوالب ومسار الإرسال.',
)
replace(
    "frontend/src/app/(dashboard)/setup/page.tsx",
    '<Link href="/setup/whatsapp" className={buttonVariants({ variant: "outline" })}>إعداد واتساب</Link>',
    '<Link href="/automations" className={buttonVariants({ variant: "outline" })}>فتح Automation</Link>',
)

setup_whatsapp = ROOT / "frontend/src/app/(dashboard)/setup/whatsapp/page.tsx"
setup_whatsapp.write_text(
    'import { redirect } from "next/navigation";\n\nexport default function WhatsAppSetupRedirect() {\n  redirect("/automations");\n}\n',
    encoding="utf-8",
)
for obsolete in [
    "frontend/src/app/(dashboard)/setup/whatsapp/actions.ts",
    "frontend/src/app/(dashboard)/setup/whatsapp/meta-embedded-signup.tsx",
]:
    path = ROOT / obsolete
    if path.exists():
        path.unlink()

# Make the old helper generic so no platform-level Meta App secret is required anywhere.
replace(
    "backend/app/services/meta_whatsapp_transport.py",
    '''def verify_meta_webhook_signature(body: bytes, signature_header: str | None) -> bool:\n    app_secret = _clean(meta_whatsapp_settings.meta_app_secret)\n    signature = _clean(signature_header)\n    if not app_secret or not signature or not signature.startswith("sha256="):\n        return False\n    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()\n    supplied = signature.removeprefix("sha256=").strip().lower()\n    return bool(supplied) and hmac.compare_digest(expected, supplied)\n\n\ndef verify_meta_webhook_challenge(mode: str | None, token: str | None) -> bool:\n    expected = _clean(meta_whatsapp_settings.meta_webhook_verify_token)\n    return bool(expected and mode == "subscribe" and token == expected)\n''',
    '''def verify_meta_webhook_signature(\n    body: bytes, signature_header: str | None, app_secret: str | None\n) -> bool:\n    secret = _clean(app_secret)\n    signature = _clean(signature_header)\n    if not secret or not signature or not signature.startswith("sha256="):\n        return False\n    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()\n    supplied = signature.removeprefix("sha256=").strip().lower()\n    return bool(supplied) and hmac.compare_digest(expected, supplied)\n''',
)

# Migration head moves to the per-clinic App Secret revision.
replace(
    "backend/app/services/operational_readiness.py",
    'EXPECTED_MIGRATION_HEAD = "0059_channel_credentials"',
    'EXPECTED_MIGRATION_HEAD = "0060_whatsapp_direct_credentials"',
)

# Native transport tests now verify scoped signatures and routes.
test_path = ROOT / "backend/tests/test_meta_native_whatsapp_transport.py"
test = test_path.read_text(encoding="utf-8")
test = test.replace("    verify_meta_webhook_challenge,\n", "")
test = test.replace(
    '''    monkeypatch.setattr(meta_whatsapp_settings, "meta_app_secret", secret)\n\n    assert verify_meta_webhook_signature(body, f"sha256={digest}") is True\n    assert verify_meta_webhook_signature(body + b"x", f"sha256={digest}") is False\n    assert verify_meta_webhook_signature(body, "sha256=deadbeef") is False\n    assert verify_meta_webhook_signature(body, None) is False\n\n\ndef test_meta_webhook_challenge_uses_platform_verify_token(\n    monkeypatch: pytest.MonkeyPatch,\n) -> None:\n    monkeypatch.setattr(meta_whatsapp_settings, "meta_webhook_verify_token", "verify-me")\n\n    assert verify_meta_webhook_challenge("subscribe", "verify-me") is True\n    assert verify_meta_webhook_challenge("subscribe", "wrong") is False\n    assert verify_meta_webhook_challenge("unsubscribe", "verify-me") is False\n\n\n''',
    '''    assert verify_meta_webhook_signature(body, f"sha256={digest}", secret) is True\n    assert verify_meta_webhook_signature(body + b"x", f"sha256={digest}", secret) is False\n    assert verify_meta_webhook_signature(body, "sha256=deadbeef", secret) is False\n    assert verify_meta_webhook_signature(body, None, secret) is False\n    assert verify_meta_webhook_signature(body, f"sha256={digest}", None) is False\n\n\n''',
)
test = test.replace('assert \'@router.get("/webhook"\' in route', 'assert \'@router.get("/webhook/{connection_id}"\' in route')
test = test.replace('assert \'@router.post("/webhook"\' in route', 'assert \'@router.post("/webhook/{connection_id}"\' in route')
test = test.replace(
    '''def test_whatsapp_credential_revision_is_short_and_hardened() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    migration = (\n        backend / "alembic/versions/0059_channel_provider_credentials.py"\n    ).read_text(encoding="utf-8")\n\n    assert 'revision: str = "0059_channel_credentials"' in migration\n    assert len("0059_channel_credentials") <= 32\n    assert "ENABLE ROW LEVEL SECURITY" in migration\n    assert "REVOKE ALL" in migration\n''',
    '''def test_whatsapp_credential_revisions_are_hardened() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    base_migration = (\n        backend / "alembic/versions/0059_channel_provider_credentials.py"\n    ).read_text(encoding="utf-8")\n    secret_migration = (\n        backend / "alembic/versions/0060_whatsapp_direct_credentials.py"\n    ).read_text(encoding="utf-8")\n\n    assert 'revision: str = "0059_channel_credentials"' in base_migration\n    assert "ENABLE ROW LEVEL SECURITY" in base_migration\n    assert "REVOKE ALL" in base_migration\n    assert 'revision: str = "0060_whatsapp_direct_credentials"' in secret_migration\n    assert 'down_revision: str | Sequence[str] | None = "0059_channel_credentials"' in secret_migration\n    assert '"app_secret_ciphertext"' in secret_migration\n''',
)
test_path.write_text(test, encoding="utf-8")

# Replace the Embedded Signup test contract with direct-connect onboarding checks.
old_test = ROOT / "backend/tests/test_whatsapp_embedded_signup_onboarding.py"
if old_test.exists():
    old_test.unlink()
new_test = ROOT / "backend/tests/test_whatsapp_direct_onboarding.py"
new_test.write_text(
    '''from pathlib import Path\n\nimport pytest\nfrom cryptography.fernet import Fernet\nfrom pydantic import ValidationError\n\nfrom app.core.meta_whatsapp_config import meta_whatsapp_settings\nfrom app.schemas.whatsapp_setup import WhatsAppDirectConnect\nfrom app.services.meta_whatsapp_onboarding import direct_setup_available\nfrom app.services.provider_credentials import decrypt_provider_secret, encrypt_provider_secret\n\n\ndef test_direct_connect_schema_rejects_non_numeric_meta_ids() -> None:\n    with pytest.raises(ValidationError):\n        WhatsAppDirectConnect(\n            app_id="app-123",\n            waba_id="123",\n            phone_number_id="456",\n            access_token="EAA-test-token-long-enough",\n            app_secret="secret-value",\n        )\n\n\ndef test_provider_app_secret_is_encrypted_at_rest(monkeypatch: pytest.MonkeyPatch) -> None:\n    key = Fernet.generate_key().decode("utf-8")\n    monkeypatch.setattr(meta_whatsapp_settings, "channel_credential_encryption_key", key)\n    secret = "clinic-meta-app-secret"\n    ciphertext = encrypt_provider_secret(secret)\n    assert ciphertext != secret\n    assert secret not in ciphertext\n    assert decrypt_provider_secret(ciphertext) == secret\n\n\ndef test_direct_setup_only_needs_platform_graph_and_encryption(monkeypatch: pytest.MonkeyPatch) -> None:\n    key = Fernet.generate_key().decode("utf-8")\n    monkeypatch.setattr(meta_whatsapp_settings, "meta_graph_api_version", "v26.0")\n    monkeypatch.setattr(meta_whatsapp_settings, "channel_credential_encryption_key", key)\n    assert direct_setup_available() is True\n\n\ndef test_embedded_signup_is_removed_from_product_routes_and_ui() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    repo = backend.parent\n    route = (backend / "app/api/routes/whatsapp_setup.py").read_text(encoding="utf-8")\n    schema = (backend / "app/schemas/whatsapp_setup.py").read_text(encoding="utf-8")\n    automation = (\n        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"\n    ).read_text(encoding="utf-8")\n    assert "embedded-signup" not in route\n    assert "EmbeddedSignup" not in schema\n    assert "Embedded Signup" not in automation\n    assert "/setup/direct" in route\n\n\ndef test_direct_onboarding_has_meta_deep_links_and_scoped_webhook() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    repo = backend.parent\n    automation = (\n        repo / "frontend/src/app/(dashboard)/automations/whatsapp-direct-onboarding.tsx"\n    ).read_text(encoding="utf-8")\n    route = (backend / "app/api/routes/whatsapp_setup.py").read_text(encoding="utf-8")\n    service = (backend / "app/services/meta_whatsapp_onboarding.py").read_text(encoding="utf-8")\n    assert "https://developers.facebook.com/apps/" in automation\n    assert "https://business.facebook.com/settings/system-users" in automation\n    assert "https://business.facebook.com/wa/manage/phone-numbers/" in automation\n    assert "whatsapp-business/wa-dev-console/" in automation\n    assert "whatsapp-business/wa-settings/" in automation\n    assert '"/webhook/{connection_id}"' in route\n    assert "app_secret_ciphertext" in service\n    assert '"webhook_verify_token"' in service\n\n\ndef test_automation_page_owns_whatsapp_onboarding() -> None:\n    backend = Path(__file__).resolve().parent.parent\n    repo = backend.parent\n    page = (repo / "frontend/src/app/(dashboard)/automations/page.tsx").read_text(encoding="utf-8")\n    setup_redirect = (repo / "frontend/src/app/(dashboard)/setup/whatsapp/page.tsx").read_text(encoding="utf-8")\n    assert "WhatsAppDirectOnboarding" in page\n    assert 'redirect("/automations")' in setup_redirect\n    assert not (repo / "frontend/src/app/(dashboard)/setup/whatsapp/meta-embedded-signup.tsx").exists()\n''',
    encoding="utf-8",
)

# Any migration-head assertions outside the dedicated 0059-history test move forward.
for path in (ROOT / "backend/tests").glob("test_*.py"):
    if path == test_path:
        continue
    text = path.read_text(encoding="utf-8")
    if "0059_channel_credentials" in text:
        path.write_text(
            text.replace("0059_channel_credentials", "0060_whatsapp_direct_credentials"),
            encoding="utf-8",
        )

print("Direct WhatsApp onboarding patch applied")
