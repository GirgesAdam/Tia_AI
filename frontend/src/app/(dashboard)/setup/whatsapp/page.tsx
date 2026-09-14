import Link from "next/link";
import { CheckCircle2, ExternalLink, Link2, MessageCircleMore } from "lucide-react";
import { redirect } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import {
  WhatsAppDirectOnboarding,
  type WhatsAppSetupState,
} from "../../automations/whatsapp-direct-onboarding";

const setupSteps = [
  {
    title: "جهّز Meta والرقم مرة واحدة",
    description: "جهّز الـMeta App والرقم في WhatsApp Cloud API لحد ما يظهر WABA ID وPhone Number ID، وبعدها جهّز App Secret وSystem User Access Token. كل خانة في Tia تحتها لينك يفتح Meta ومعاه اسم المسار اللي تمشي عليه.",
    icon: ExternalLink,
  },
  {
    title: "خلّي Tia تتحقق وتربط",
    description: "الصق القيم واضغط تحقق واربط. Tia هتتأكد من الـToken والصلاحيات والرقم قبل ما تحفظ الأسرار مشفرة.",
    icon: CheckCircle2,
  },
  {
    title: "فعّل الـWebhook",
    description: "بعد الربط، Tia هتديك Callback URL وVerify Token جاهزين للنسخ. ضيفهم في Meta مرة واحدة واضغط إنهاء الإعداد داخل Tia.",
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
        description="ربط مباشر مع Meta Cloud API من غير مزود وسيط أو اشتراك إضافي لطرف ثالث. الإعداد بيتعمل مرة واحدة وTia هتراجع كل خطوة قبل التشغيل."
      />

      <Card className="mb-6 border-teal-200 bg-teal-50/40">
        <CardContent className="p-5">
          <div className="flex items-start gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-emerald-600 text-white">
              <MessageCircleMore size={22} />
            </span>
            <div>
              <b className="text-lg text-slate-950">مفيش Provider مدفوع بين Tia وMeta</b>
              <p className="mt-1 text-sm leading-6 text-[var(--muted)]">
                الربط مباشر مع Meta Cloud API. مش محتاج 360dialog أو Twilio أو أي BSP باشتراك شهري. العيادة بتستخدم حساب Meta والرقم بتوعها، وتدفع فقط أي رسوم WhatsApp/Meta الأصلية المطبقة على استخدامها. بسبب إن Meta Embedded Signup غير متاح لنا حاليًا، Tia هتوجّهك في الإعداد اليدوي بأقل عدد ممكن من الخطوات ومن غير تخمين.
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
        <Link href="/setup" className={cn(buttonVariants({ variant: "outline" }))}>
          الرجوع لإعدادات العيادة
        </Link>
        {state.ready_for_automations && (
          <Link href="/automations" className={cn(buttonVariants())}>
            افتح Automation
          </Link>
        )}
      </div>
    </>
  );
}
