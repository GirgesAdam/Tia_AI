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
import type {
  AutomationOperationsOverview,
  AutomationRule,
  ChannelConnection,
} from "@/lib/types";
import { MetaEmbeddedSignup, type EmbeddedSignupConfig } from "./meta-embedded-signup";

const META_SUPPORT_URL = "https://business.facebook.com/business-support-home/";

function providerHealth(connection: ChannelConnection | null) {
  const raw = connection?.config_json?.provider_health;
  return raw && typeof raw === "object" && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : null;
}

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
  const [connections, rules, overview, signupConfig, ctx] = await Promise.all([
    tiaRequest<ChannelConnection[]>("/channels/connections"),
    tiaRequest<AutomationRule[]>("/automations/rules"),
    tiaRequest<AutomationOperationsOverview>("/automations/overview"),
    tiaRequest<EmbeddedSignupConfig>("/channels/whatsapp/setup/embedded-signup/config"),
    getAppContext(),
  ]);

  const admin = ctx.workspace.role === "admin";
  const connection =
    connections.find(
      (item) => item.channel === "whatsapp" && item.status !== "disconnected",
    ) || null;
  const health = providerHealth(connection);
  const providerState = typeof health?.state === "string" ? health.state : null;
  const providerError =
    typeof health?.current_error === "string" ? health.current_error : null;
  const providerErrorCode =
    health?.current_error_code == null ? null : String(health.current_error_code);

  const enabledWhatsAppRules = rules.filter(
    (rule) => rule.enabled && (rule.channel === "whatsapp" || rule.channel === "auto"),
  );
  const connectionNeedsAttention = Boolean(
    connection &&
      (providerState === "disabled" ||
        providerState === "degraded" ||
        providerErrorCode === "131031"),
  );
  const connectionReady = Boolean(connection && connection.status === "active" && !connectionNeedsAttention);
  const workerReady = overview.worker_state === "healthy" || overview.worker_state === "not_required";

  const templateConfig = connection?.config_json?.template_statuses;
  const templateStatuses =
    templateConfig && typeof templateConfig === "object" && !Array.isArray(templateConfig)
      ? (templateConfig as Record<string, unknown>)
      : {};
  const enabledTemplates = enabledWhatsAppRules
    .map((rule) => rule.template_name)
    .filter(Boolean);
  const templatesKnown = enabledTemplates.length > 0 && enabledTemplates.every((name) => name in templateStatuses);
  const templatesApproved =
    enabledTemplates.length === 0 ||
    (templatesKnown &&
      enabledTemplates.every((name) => String(templateStatuses[name]).toLowerCase() === "approved"));

  const fullyReady = connectionReady && workerReady && templatesApproved;

  const steps: Array<{
    title: string;
    description: string;
    owner: "admin" | "tia";
    status: "done" | "pending" | "attention";
  }> = [
    {
      title: "ربط حساب Meta ورقم العيادة",
      description: connection
        ? "تم تسجيل اتصال واتساب للعيادة داخل Tia."
        : "مدير العيادة يسجل دخوله إلى Meta ويختار الـBusiness ورقم واتساب فقط. Tia تتولى التفاصيل التقنية بعد ذلك.",
      owner: "admin",
      status: connection ? "done" : "attention",
    },
    {
      title: "فحص حالة حساب واتساب",
      description: connectionNeedsAttention
        ? "Meta أوقفت أو قيّدت الاتصال. نحتاج من مدير العيادة حل المراجعة المطلوبة داخل Meta فقط."
        : connection
          ? "الاتصال غير موقوف بسبب خطأ دائم من مزود واتساب."
          : "يبدأ تلقائيًا بعد ربط الحساب.",
      owner: connectionNeedsAttention ? "admin" : "tia",
      status: connectionNeedsAttention ? "attention" : connection ? "done" : "pending",
    },
    {
      title: "تجهيز قوالب الرسائل",
      description: templatesApproved
        ? "القوالب المطلوبة للقواعد المفعلة جاهزة."
        : templatesKnown
          ? "بعض القوالب ما زالت في مراجعة Meta أو تحتاج مراجعة. Tia تتابع الحالة وتعرض فقط ما يحتاج تدخل المدير."
          : "Tia تتحقق من القوالب المطلوبة للقواعد المفعلة وتمنع التشغيل قبل جاهزيتها.",
      owner: "tia",
      status: templatesApproved ? "done" : "pending",
    },
    {
      title: "محرك Automation",
      description: workerReady
        ? "محرك التنفيذ متصل وجاهز لتخطيط وتشغيل الرسائل."
        : "ربط وتشغيل محرك التنفيذ مسؤولية Tia، وليس مدير العيادة.",
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

      {!admin ? (
        <Card>
          <CardContent className="p-5 text-sm text-[var(--muted)]">
            إعداد واتساب متاح لمدير العيادة فقط.
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className={fullyReady ? "mb-5 border-emerald-200 bg-emerald-50/60" : "mb-5 border-slate-200 bg-slate-50/70"}>
            <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  {fullyReady ? (
                    <CheckCircle2 size={20} className="text-emerald-700" />
                  ) : connectionNeedsAttention ? (
                    <CircleAlert size={20} className="text-rose-700" />
                  ) : (
                    <Clock3 size={20} className="text-amber-700" />
                  )}
                  <b className="text-lg">
                    {fullyReady
                      ? "واتساب جاهز للـAutomation"
                      : connectionNeedsAttention
                        ? "واتساب يحتاج إجراء من مدير العيادة"
                        : "إعداد واتساب لم يكتمل بعد"}
                  </b>
                  <Badge tone={fullyReady ? "green" : connectionNeedsAttention ? "red" : "yellow"}>
                    {fullyReady ? "جاهز" : connectionNeedsAttention ? "تحتاج مراجعة" : "إعداد"}
                  </Badge>
                </div>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted)]">
                  لن نطلب منك WABA ID أو Phone Number ID أو Tokens أو إعداد n8n. هذه تفاصيل تشغيلية تتعامل معها Tia.
                </p>
                {connection && (
                  <p className="mt-2 text-xs text-[var(--muted)]">
                    الاتصال الحالي: {connection.display_name || "WhatsApp"} · {connection.status === "active" ? "نشط" : "متوقف"}
                  </p>
                )}
              </div>

              {connectionNeedsAttention && (
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
                  <div key={step.title} className="flex gap-3 rounded-2xl border border-[var(--border)] p-4">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-black text-slate-700">
                      {index + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <b>{step.title}</b>
                        <Badge tone={statusTone(step.status)}>{statusLabel(step.status)}</Badge>
                        <Badge tone="gray">{step.owner === "admin" ? "مدير العيادة" : "Tia"}</Badge>
                      </div>
                      <p className="mt-1 text-sm leading-6 text-[var(--muted)]">{step.description}</p>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><ShieldCheck size={18} /> ما الذي يحتاجه مدير العيادة؟</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm leading-6 text-[var(--muted)]">
                  <p><b className="text-slate-900">1.</b> تسجيل الدخول إلى Meta واختيار الـBusiness ورقم واتساب.</p>
                  <p><b className="text-slate-900">2.</b> تنفيذ Business Verification أو Request Review فقط لو Meta طلبت ذلك.</p>
                  <p><b className="text-slate-900">3.</b> التدخل فقط لو Meta رفضت Template وطلبت تعديلًا أو مراجعة.</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Workflow size={18} /> ما الذي تتولاه Tia؟</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm leading-6 text-[var(--muted)]">
                  <p>ربط الاتصال بالـworkspace الصحيح.</p>
                  <p>إعداد وتشغيل محرك الـAutomation والـoutbox.</p>
                  <p>متابعة حالة القوالب والـprovider health.</p>
                  <p>منع الإرسال عند غياب WhatsApp opt-in أو عند توقف Meta.</p>
                  <p>إيقاف retries الدائمة وتحويل المتابعة للموظف عند الحاجة.</p>
                </CardContent>
              </Card>

              {!connection && (
                <Card className="border-teal-200 bg-teal-50/60">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-2 font-bold text-slate-950"><Smartphone size={18} /> الخطوة التالية</div>
                    <p className="mt-2 mb-3 text-sm leading-6 text-[var(--muted)]">
                      افتح شاشة Meta الرسمية واختار Business العيادة ورقم واتساب فقط.
                    </p>
                    <MetaEmbeddedSignup config={signupConfig} />
                  </CardContent>
                </Card>
              )}
            </div>
          </div>

          {connectionNeedsAttention && (providerError || providerErrorCode) && (
            <Card className="mt-5 border-rose-200 bg-rose-50/60">
              <CardContent className="p-5 text-sm text-rose-950">
                <b>آخر مشكلة من Meta</b>
                <p className="mt-2 leading-6">{providerError || "تم إيقاف الاتصال من مزود واتساب."}</p>
                {providerErrorCode && <p className="mt-1 text-xs">الكود: {providerErrorCode}</p>}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </>
  );
}
