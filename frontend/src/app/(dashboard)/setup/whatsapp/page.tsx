import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock3,
  ExternalLink,
  ShieldCheck,
  Smartphone,
  Workflow,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { AutomationOperationsOverview } from "@/lib/types";
import { MetaEmbeddedSignup, type EmbeddedSignupConfig } from "./meta-embedded-signup";

const META_SUPPORT_URL = "https://business.facebook.com/business-support-home/";

type WhatsAppSetupState = {
  connection_status: "active" | "paused" | "disconnected" | null;
  connected: boolean;
  display_name: string | null;
  display_phone_number: string | null;
  verified_name: string | null;
  provider_health_state: string | null;
  provider_error_code: string | null;
  provider_error: string | null;
  embedded_signup_available: boolean;
  provider_credentials_ready: boolean;
  transport_ready: boolean;
  templates_ready: boolean;
  ready_for_automations: boolean;
  admin_action:
    | "connect_meta"
    | "resolve_meta_restriction"
    | "wait_for_template_review"
    | "none";
  admin_message: string | null;
  system_message: string | null;
};

function statusTone(status: "done" | "pending" | "attention") {
  if (status === "done") return "green" as const;
  if (status === "attention") return "red" as const;
  return "yellow" as const;
}

function statusLabel(status: "done" | "pending" | "attention") {
  if (status === "done") return "جاهز";
  if (status === "attention") return "مطلوب منك";
  return "Tia بتجهزه";
}

export default async function WhatsAppSetupPage() {
  const ctx = await getAppContext();
  const admin = ctx.workspace.role === "admin";

  if (!admin) {
    return (
      <>
        <PageHeader
          title="إعداد واتساب"
          description="إعداد واتساب متاح لمدير العيادة فقط."
          action={
            <Link href="/setup" className={buttonVariants({ variant: "outline" })}>
              <ArrowRight size={16} /> إعدادات العيادة
            </Link>
          }
        />
        <Card>
          <CardContent className="p-5 text-sm text-[var(--muted)]">
            اطلب من مدير العيادة إكمال ربط Meta. لا يحتاج أي موظف لإدخال Tokens أو IDs.
          </CardContent>
        </Card>
      </>
    );
  }

  const [setupState, overview, signupConfig] = await Promise.all([
    tiaRequest<WhatsAppSetupState>("/channels/whatsapp/setup"),
    tiaRequest<AutomationOperationsOverview>("/automations/overview"),
    tiaRequest<EmbeddedSignupConfig>("/channels/whatsapp/setup/embedded-signup/config"),
  ]);

  const workerReady =
    overview.worker_state === "healthy" || overview.worker_state === "not_required";
  const fullyReady = setupState.ready_for_automations && workerReady;
  const adminNeedsAttention = setupState.admin_action !== "none";
  const needsMetaReconnect = setupState.admin_action === "connect_meta";
  const needsMetaReview = setupState.admin_action === "resolve_meta_restriction";
  const needsTemplateReview = setupState.admin_action === "wait_for_template_review";

  const steps: Array<{
    title: string;
    description: string;
    owner: "admin" | "tia";
    status: "done" | "pending" | "attention";
  }> = [
    {
      title: "ربط حساب Meta ورقم العيادة",
      description: needsMetaReconnect
        ? setupState.admin_message ||
          "سجّل الدخول إلى Meta واختَر Business العيادة ورقم واتساب فقط."
        : setupState.connected
          ? `تم ربط ${setupState.verified_name || setupState.display_name || "رقم واتساب"} داخل Tia.`
          : "سجّل الدخول إلى Meta واختَر Business العيادة ورقم واتساب فقط.",
      owner: needsMetaReconnect || !setupState.connected ? "admin" : "tia",
      status: needsMetaReconnect || !setupState.connected ? "attention" : "done",
    },
    {
      title: "فحص الاتصال ومسار الإرسال",
      description: needsMetaReview
        ? setupState.admin_message || "Meta تحتاج مراجعة من مدير العيادة."
        : setupState.transport_ready
          ? "Tia تحققت من الرقم والـprovider ومسار الإرسال جاهز."
          : setupState.system_message || "Tia بتجهز الاتصال وتتحقق من Meta تلقائيًا.",
      owner: needsMetaReview ? "admin" : "tia",
      status: needsMetaReview ? "attention" : setupState.transport_ready ? "done" : "pending",
    },
    {
      title: "قوالب الرسائل",
      description: needsTemplateReview
        ? setupState.admin_message || "Meta تحتاج تعديل أو مراجعة Template."
        : setupState.templates_ready
          ? "القوالب المطلوبة للـAutomations المفعلة Approved وجاهزة."
          : setupState.system_message || "Tia تتابع حالة القوالب تلقائيًا مع Meta.",
      owner: needsTemplateReview ? "admin" : "tia",
      status: needsTemplateReview ? "attention" : setupState.templates_ready ? "done" : "pending",
    },
    {
      title: "محرك Automation",
      description: workerReady
        ? "محرك التنفيذ متصل وجاهز لتخطيط وتشغيل الرسائل."
        : "تشغيل ومتابعة الـworker مسؤولية Tia، وليس مدير العيادة.",
      owner: "tia",
      status: workerReady ? "done" : "pending",
    },
    {
      title: "تشغيل الرسائل بأمان",
      description: fullyReady
        ? "واتساب والـAutomation جاهزين. القواعد المفعلة ستعمل بتوقيتاتها الحالية مع فحوصات الأمان قبل الإرسال."
        : "Tia لن تعتبر الإعداد مكتملًا قبل جاهزية الاتصال والقوالب ومحرك التنفيذ.",
      owner: "tia",
      status: fullyReady ? "done" : "pending",
    },
  ];

  return (
    <>
      <PageHeader
        title="إعداد واتساب"
        description="اربط رقم العيادة بخطوات بسيطة. مدير العيادة يتعامل فقط مع الخطوات التي Meta تشترط أن ينفذها بنفسه."
        action={
          <Link href="/setup" className={buttonVariants({ variant: "outline" })}>
            <ArrowRight size={16} /> إعدادات العيادة
          </Link>
        }
      />

      <Card
        className={
          fullyReady
            ? "mb-5 border-emerald-200 bg-emerald-50/60"
            : adminNeedsAttention
              ? "mb-5 border-rose-200 bg-rose-50/50"
              : "mb-5 border-slate-200 bg-slate-50/70"
        }
      >
        <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              {fullyReady ? (
                <CheckCircle2 size={20} className="text-emerald-700" />
              ) : adminNeedsAttention ? (
                <CircleAlert size={20} className="text-rose-700" />
              ) : (
                <Clock3 size={20} className="text-amber-700" />
              )}
              <b className="text-lg">
                {fullyReady
                  ? "واتساب جاهز للـAutomation"
                  : adminNeedsAttention
                    ? "في خطوة محتاجة مدير العيادة"
                    : "Tia بتكمّل إعداد واتساب"}
              </b>
              <Badge tone={fullyReady ? "green" : adminNeedsAttention ? "red" : "yellow"}>
                {fullyReady ? "جاهز" : adminNeedsAttention ? "مطلوب إجراء" : "جاري الإعداد"}
              </Badge>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted)]">
              لن نطلب منك WABA ID أو Phone Number ID أو Tokens أو إعداد n8n. هذه تفاصيل تشغيلية تتعامل معها Tia.
            </p>
            {setupState.connected && (
              <p className="mt-2 text-xs text-[var(--muted)]">
                الاتصال الحالي: {setupState.display_name || "WhatsApp"}
                {setupState.display_phone_number ? ` · ${setupState.display_phone_number}` : ""} ·{" "}
                {setupState.connection_status === "active" ? "نشط" : "قيد التجهيز"}
              </p>
            )}
            {setupState.system_message && !adminNeedsAttention && (
              <p className="mt-2 text-sm text-amber-800">{setupState.system_message}</p>
            )}
          </div>

          {needsMetaReview && (
            <a
              href={META_SUPPORT_URL}
              target="_blank"
              rel="noreferrer"
              className={buttonVariants({ variant: "outline" })}
            >
              فتح Meta Business Support <ExternalLink size={15} />
            </a>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>خطوات الإعداد</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {steps.map((step, index) => (
              <div
                key={step.title}
                className="flex gap-3 rounded-2xl border border-[var(--border)] p-4"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-black text-slate-700">
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <b>{step.title}</b>
                    <Badge tone={statusTone(step.status)}>{statusLabel(step.status)}</Badge>
                    <Badge tone="gray">
                      {step.owner === "admin" ? "مدير العيادة" : "Tia"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-[var(--muted)]">
                    {step.description}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {(needsMetaReconnect || !setupState.connected) && (
            <Card className="border-teal-200 bg-teal-50/60">
              <CardContent className="p-5">
                <div className="flex items-center gap-2 font-bold text-slate-950">
                  <Smartphone size={18} /> {setupState.connected ? "إعادة ربط Meta" : "ربط واتساب"}
                </div>
                <p className="mt-2 mb-3 text-sm leading-6 text-[var(--muted)]">
                  افتح شاشة Meta الرسمية واختار Business العيادة ورقم واتساب فقط. Tia هتكمل باقي الإعداد تلقائيًا.
                </p>
                <MetaEmbeddedSignup config={signupConfig} />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck size={18} /> ما الذي يحتاجه مدير العيادة؟
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm leading-6 text-[var(--muted)]">
              <p>
                <b className="text-slate-900">1.</b> تسجيل الدخول إلى Meta واختيار الـBusiness ورقم واتساب.
              </p>
              <p>
                <b className="text-slate-900">2.</b> تنفيذ Business Verification أو Request Review فقط لو Meta طلبت ذلك.
              </p>
              <p>
                <b className="text-slate-900">3.</b> التدخل فقط لو Meta رفضت Template وطلبت تعديلًا أو مراجعة.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Workflow size={18} /> ما الذي تتولاه Tia؟
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm leading-6 text-[var(--muted)]">
              <p>ربط الاتصال بالـworkspace الصحيح وتخزين بيانات Meta بأمان.</p>
              <p>استقبال Webhooks والإرسال من خلال الـnative transport الخاص بـTia.</p>
              <p>متابعة حالة القوالب والـprovider health تلقائيًا.</p>
              <p>منع الإرسال عند غياب WhatsApp opt-in أو عند توقف Meta.</p>
              <p>إدارة retries والـoutbox وتحويل المتابعة للموظف عند الحاجة.</p>
            </CardContent>
          </Card>
        </div>
      </div>

      {adminNeedsAttention && setupState.admin_message && (
        <Card className="mt-5 border-rose-200 bg-rose-50/60">
          <CardContent className="p-5 text-sm text-rose-950">
            <b>المطلوب منك الآن</b>
            <p className="mt-2 leading-6">{setupState.admin_message}</p>
            {setupState.provider_error_code && (
              <p className="mt-1 text-xs">Meta code: {setupState.provider_error_code}</p>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}
