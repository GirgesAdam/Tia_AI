"use client";

import { useActionState, useState } from "react";
import { CheckCircle2, Copy, ExternalLink, KeyRound, Link2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  connectWhatsappDirectAction,
  finishWhatsappDirectSetupAction,
} from "./actions";
import type { WhatsAppSetupActionState } from "./actions";

export type WhatsAppSetupState = {
  connected: boolean;
  connection_status: "active" | "paused" | "disconnected" | null;
  display_name: string | null;
  display_phone_number: string | null;
  verified_name: string | null;
  provider_health_state: string | null;
  provider_error_code: string | null;
  provider_error: string | null;
  direct_setup_available: boolean;
  provider_credentials_ready: boolean;
  transport_ready: boolean;
  templates_ready: boolean;
  ready_for_automations: boolean;
  meta_app_id: string | null;
  webhook_callback_url: string | null;
  webhook_verify_token: string | null;
  webhook_verified: boolean;
  admin_action:
    | "connect_meta_direct"
    | "configure_webhook"
    | "resolve_meta_restriction"
    | "wait_for_template_review"
    | "none";
  admin_message: string | null;
  system_message: string | null;
};

const APPS_URL = "https://developers.facebook.com/apps/";
const SYSTEM_USERS_URL = "https://business.facebook.com/settings/system-users";
const CURRENT_API_TESTING_URL =
  "https://developers.facebook.com/apps/1370437594582187/use_cases/customize/api-testing-v2/?product_route=whatsapp-business&business_id=2086664822245784&use_case_enum=WHATSAPP_BUSINESS_MESSAGING&selected_tab=api-testing-v2";
const CURRENT_WHATSAPP_CONFIGURATION_URL =
  "https://developers.facebook.com/apps/1370437594582187/use_cases/customize/wa-configurations-v2/?use_case_enum=WHATSAPP_BUSINESS_MESSAGING&selected_tab=wa-configurations-v2&product_route=whatsapp-business&business_id=2086664822245784";
const initialSetupActionState: WhatsAppSetupActionState = { ok: false, message: null };

function DirectLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xs font-bold !text-teal-700 underline underline-offset-2"
    >
      {children} <ExternalLink size={12} />
    </a>
  );
}

function CopyValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex gap-2">
      <Input value={value} readOnly className="font-mono text-xs" dir="ltr" />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={async () => {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1600);
        }}
      >
        <Copy size={14} /> {copied ? "تم" : "نسخ"}
      </Button>
    </div>
  );
}

export function WhatsAppDirectOnboarding({ state }: { state: WhatsAppSetupState }) {
  const [appId, setAppId] = useState(state.meta_app_id || "");
  const [appSecret, setAppSecret] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [connectState, connectAction, connectPending] = useActionState(
    connectWhatsappDirectAction,
    initialSetupActionState,
  );
  const [finishState, finishAction, finishPending] = useActionState(
    finishWhatsappDirectSetupAction,
    initialSetupActionState,
  );

  const cleanAppId = appId.trim();
  const appDashboard = cleanAppId ? `${APPS_URL}${cleanAppId}/` : APPS_URL;
  const appSecretUrl = cleanAppId
    ? `${APPS_URL}${cleanAppId}/settings/basic/`
    : APPS_URL;
  const webhookConfigUrl = CURRENT_WHATSAPP_CONFIGURATION_URL;

  const needsCredentials =
    !state.connected || state.admin_action === "connect_meta_direct" || !state.provider_credentials_ready;
  const needsWebhook = state.connected && !state.webhook_verified;

  if (state.ready_for_automations) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="flex items-center gap-2 font-black text-emerald-950">
          <CheckCircle2 size={20} /> واتساب مربوط وجاهز للـAutomation
        </div>
        <p className="mt-2 text-sm leading-6 text-emerald-900">
          {state.verified_name || state.display_phone_number || "رقم العيادة"} متصل بـMeta، والـWebhook ومسار الإرسال والقوالب المطلوبة جاهزين.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {needsCredentials && (
        <form action={connectAction} className="space-y-5 rounded-2xl border border-teal-200 bg-teal-50/50 p-5">
          <div>
            <div className="flex items-center gap-2 font-black text-slate-950">
              <KeyRound size={18} /> 1. اربط Meta مباشرة
            </div>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              الربط مباشر مع Meta Cloud API من غير طرف وسيط. العيادة تملك Meta App والرقم، وTia تستخدم Cloud API مباشرة. البيانات السرية تتخزن مشفرة ومش هتظهر بعد الحفظ.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 text-sm font-bold text-slate-900">
              <span>Meta App ID</span>
              <Input
                name="app_id"
                value={appId}
                onChange={(event) => setAppId(event.target.value)}
                inputMode="numeric"
                dir="ltr"
                placeholder="1234567890123456"
                required
              />
              <DirectLink href={APPS_URL}>افتح My Apps وخد App ID</DirectLink>
            </label>

            <label className="space-y-2 text-sm font-bold text-slate-900">
              <span>App Secret</span>
              <Input
                name="app_secret"
                type="password"
                dir="ltr"
                autoComplete="off"
                value={appSecret}
                onChange={(event) => setAppSecret(event.target.value)}
                required
              />
              <DirectLink href={appSecretUrl}>افتح App Settings → Basic مباشرة</DirectLink>
            </label>

            <label className="space-y-2 text-sm font-bold text-slate-900">
              <span>WhatsApp Business Account ID (WABA ID)</span>
              <Input
                name="waba_id"
                inputMode="numeric"
                dir="ltr"
                value={wabaId}
                onChange={(event) => setWabaId(event.target.value)}
                required
              />
              <DirectLink href={CURRENT_API_TESTING_URL}>افتح WhatsApp API Testing وخد WABA ID</DirectLink>
            </label>

            <label className="space-y-2 text-sm font-bold text-slate-900">
              <span>Phone Number ID</span>
              <Input
                name="phone_number_id"
                inputMode="numeric"
                dir="ltr"
                value={phoneNumberId}
                onChange={(event) => setPhoneNumberId(event.target.value)}
                required
              />
              <DirectLink href={CURRENT_API_TESTING_URL}>افتح نفس صفحة API Testing وخد Phone Number ID</DirectLink>
            </label>
          </div>

          <label className="block space-y-2 text-sm font-bold text-slate-900">
            <span>System User Access Token</span>
            <Input
              name="access_token"
              type="password"
              dir="ltr"
              autoComplete="off"
              value={accessToken}
              onChange={(event) => setAccessToken(event.target.value)}
              required
            />
            <div className="text-xs font-normal text-[var(--muted)]">
              <p>
                اعمل System User بصلاحية Admin، Assign Assets للـApp وWhatsApp Account، وبعدها Generate Token بصلاحيات whatsapp_business_management وwhatsapp_business_messaging.
              </p>
              <div className="mt-2 w-full text-right">
                <DirectLink href={SYSTEM_USERS_URL}>افتح System Users مباشرة</DirectLink>
              </div>
            </div>
          </label>

          <div className="rounded-xl border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-600">
            <b className="text-slate-900">قبل ما تضغط ربط:</b> Tia هتتأكد من Meta إن الـToken تابع لنفس App، وإن الصلاحيات موجودة، وإن Phone Number ID تابع للـWABA ID. لو أي حاجة غلط هتقولك بالظبط إيه اللي محتاج يتصلح.
          </div>

          {connectState.message && (
            <p className={`text-sm leading-6 ${connectState.ok ? "text-emerald-700" : "text-rose-700"}`}>
              {connectState.message}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={connectPending || !state.direct_setup_available}>
              {connectPending ? "Tia بتتحقق..." : "تحقق واربط"}
            </Button>
            <DirectLink href={appDashboard}>افتح الـMeta App</DirectLink>
            {!state.direct_setup_available && (
              <span className="text-xs text-rose-700">إعداد التشفير أو Graph API في Tia غير مكتمل على السيرفر.</span>
            )}
          </div>
        </form>
      )}

      {needsWebhook && state.webhook_callback_url && state.webhook_verify_token && (
        <form action={finishAction} className="space-y-4 rounded-2xl border border-sky-200 bg-sky-50/50 p-5">
          <div>
            <div className="flex items-center gap-2 font-black text-slate-950">
              <Link2 size={18} /> 2. اربط الـWebhook
            </div>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              Tia جهزت الرابط والـVerify Token مخصوص للعيادة دي. افتح WhatsApp Configuration، الصق القيمتين، واضغط Verify and Save، وبعدها Subscribe لحقل messages.
            </p>
          </div>

          <div className="space-y-2">
            <div className="text-xs font-bold text-slate-700">Callback URL</div>
            <CopyValue value={state.webhook_callback_url} />
          </div>
          <div className="space-y-2">
            <div className="text-xs font-bold text-slate-700">Verify Token</div>
            <CopyValue value={state.webhook_verify_token} />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <DirectLink href={webhookConfigUrl}>افتح WhatsApp → Configuration مباشرة</DirectLink>
            <span className="text-xs text-[var(--muted)]">بعد Verify and Save: Manage → messages → Subscribe.</span>
          </div>

          {finishState.message && (
            <p className={`text-sm ${finishState.ok ? "text-emerald-700" : "text-rose-700"}`}>
              {finishState.message}
            </p>
          )}

          <Button type="submit" disabled={finishPending}>
            {finishPending ? "Tia بتتحقق..." : "تم في Meta — تحقق وكمل"}
          </Button>
        </form>
      )}

      {state.connected && state.webhook_verified && !state.ready_for_automations && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
          <div className="flex items-center gap-2 font-black text-amber-950">
            <ShieldCheck size={18} /> 3. Tia بتكمّل الفحص
          </div>
          <p className="mt-2 text-sm leading-6 text-amber-900">
            {state.system_message || state.admin_message || "الـWebhook اتأكد. Tia بتفحص الرقم والقوالب ومسار الإرسال قبل ما تسمح للـAutomation يبعث."}
          </p>
        </div>
      )}
    </div>
  );
}
