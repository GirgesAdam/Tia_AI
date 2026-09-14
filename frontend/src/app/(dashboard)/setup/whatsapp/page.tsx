import Link from "next/link";
import { CheckCircle2, ExternalLink, Link2, MessageCircleMore } from "lucide-react";
import { redirect } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import {
  WhatsAppDirectOnboarding,
  type WhatsAppSetupState,
} from "../../automations/whatsapp-direct-onboarding";

const setupSteps = [
  {
    title: "جهّز بيانات Meta",
    description: "هتحتاج App ID وApp Secret وWABA ID وPhone Number ID وSystem User Access Token. كل خانة تحتها لينك مباشر للمكان اللي هتجيب منه القيمة.",
    icon: ExternalLink,
  },
  {
    title: "خلّي Tia تتحقق وتربط",
    description: "الصق القيم واضغط تحقق واربط. Tia هتتأكد إن الـToken والصلاحيات والرقم تابعين لنفس حساب Meta قبل ما تحفظ أي إعداد.",
    icon: CheckCircle2,
  },
  {
    title: "فعّل الـWebhook",
    description: "بعد الربط، Tia هتديك Callback URL وVerify Token جاهزين للنسخ. ضيفهم في Meta واضغط إنهاء الإعداد داخل Tia.",
    icon: Link2,
  },
];

export default async function WhatsAppSetupPage() {
  const ctx = await getAppContext();
  if (ctx.workspace.role !== "admin") {
    redirect("/setup");
  }

  const state = await tiaRequest<WhatsAppSetupState>("/channels/whatsapp/setup");

  return (
    <>
      <PageHeader
        title="ربط WhatsApp"
        description="إعداد مرة واحدة. امشِ بالترتيب، وTia هتوضح لك كل خطوة وتتحقق من البيانات قبل التشغيل."
      />

      <Card className="mb-6 border-teal-200 bg-teal-50/40">
        <CardContent className="p-5">
          <div className="flex items-start gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-emerald-600 text-white">
              <MessageCircleMore size={22} />
            </span>
            <div>
              <b className="text-lg text-slate-950">قبل ما تبدأ</b>
              <p className="mt-1 text-sm leading-6 text-[var(--muted)]">
                الربط الحالي مباشر مع Meta Cloud API. مش محتاج أي طرف وسيط، لكن Meta بتطلب إن بيانات التطبيق والرقم تتجهز يدويًا. Tia هتفتح لك الصفحات المطلوبة وتقول لك بالضبط إيه القيمة اللي تنسخها.
              </p>
            </div>
          </div>

          <div className="mt-5 grid gap-3 lg:grid-cols-3">
            {setupSteps.map((step, index) => {
              const Icon = step.icon;
              return (
                <div key={step.title} className="rounded-2xl border border-white bg-white p-4 shadow-sm">
                  <div className="flex items-center gap-2 font-black text-slate-950">
                    <span className="grid size-7 place-items-center rounded-lg bg-slate-900 text-xs text-white">{index + 1}</span>
                    <Icon size={17} /> {step.title}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{step.description}</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <WhatsAppDirectOnboarding state={state} />

      <div className="mt-6 flex flex-wrap gap-3">
        <Button asChild variant="outline">
          <Link href="/setup">الرجوع لإعدادات العيادة</Link>
        </Button>
        {state.ready_for_automations && (
          <Button asChild>
            <Link href="/automations">افتح Automation</Link>
          </Button>
        )}
      </div>
    </>
  );
}
