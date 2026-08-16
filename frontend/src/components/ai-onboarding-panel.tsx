"use client";

import { useActionState, useEffect } from "react";
import { Bot, CheckCircle2, LoaderCircle, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import { onboardingAiAction } from "@/app/(dashboard)/setup/actions";
import {
  initialOnboardingAIActionState,
  type OnboardingAIActionState,
} from "@/lib/onboarding-ai-types";

const summaryLabels: Record<string, string> = {
  branches: "فروع",
  services: "خدمات",
  doctors: "دكاترة",
  branch_schedules: "جداول فروع",
  doctor_schedules: "جداول دكاترة",
  booking_settings: "إعدادات الحجز",
};

function SubmitButton({
  label,
  mode,
  secondary = false,
}: {
  label: string;
  mode: string;
  secondary?: boolean;
}) {
  return (
    <button
      type="submit"
      name="mode"
      value={mode}
      className={
        secondary
          ? "rounded-xl border border-[var(--border)] bg-white px-4 py-2 text-sm font-bold"
          : "rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-bold text-white"
      }
    >
      {label}
    </button>
  );
}

export function AIOnboardingPanel() {
  const router = useRouter();
  const [state, action, pending] = useActionState<
    OnboardingAIActionState,
    FormData
  >(onboardingAiAction, initialOnboardingAIActionState);

  useEffect(() => {
    if (state.response?.readiness_refresh_required) router.refresh();
  }, [router, state.response]);

  const response = state.response;
  const summary = response?.plan_summary || {};
  const terminal = response?.status === "completed" || response?.status === "cancelled";

  return (
    <section className="mb-6 overflow-hidden rounded-3xl border border-teal-200 bg-gradient-to-br from-teal-50 to-white">
      <div className="border-b border-teal-100 p-5">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-teal-700 text-white">
            <Bot size={22} />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-black">إعداد العيادة مع Tia</h2>
              <Sparkles size={16} className="text-teal-700" />
            </div>
            <p className="mt-1 text-sm text-slate-600">
              اشرح إعدادات العيادة بطريقتك. Tia هتكوّن خطة، تعرضها عليك،
              ومش هتنفذ أي تعديل إلا بعد تأكيد Admin واضح.
            </p>
          </div>
        </div>
      </div>

      <form action={action} className="space-y-4 p-5">
        <input type="hidden" name="session_id" value={terminal ? "" : response?.session_id || ""} />
        <input type="hidden" name="version" value={terminal ? "" : response?.version || ""} />

        {response && (
          <div className="rounded-2xl border border-teal-100 bg-white p-4">
            <div className="mb-2 text-xs font-bold uppercase tracking-wide text-teal-700">
              Tia
            </div>
            <p className="whitespace-pre-wrap text-sm leading-7">
              {response.assistant_message}
            </p>

            {Object.keys(summary).length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {Object.entries(summary).map(([key, value]) => (
                  <span
                    key={key}
                    className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold"
                  >
                    {summaryLabels[key] || key}:{" "}
                    {typeof value === "boolean" ? (value ? "نعم" : "لا") : value}
                  </span>
                ))}
              </div>
            )}

            {!!response.missing_information.length && (
              <ul className="mt-4 list-disc space-y-1 pr-5 text-xs text-amber-800">
                {response.missing_information.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}

            {response.status === "completed" && (
              <div className="mt-4 flex items-center gap-2 text-sm font-bold text-emerald-700">
                <CheckCircle2 size={18} />
                التعديلات اتنفذت فعليًا في إعدادات Workspace.
              </div>
            )}
          </div>
        )}

        {state.error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {state.error}
          </div>
        )}

        <textarea
          name="message"
          rows={4}
          className="w-full rounded-2xl border border-[var(--border)] bg-white p-3 text-sm"
          placeholder={
            terminal
              ? "اكتب إعدادات الخطة الجديدة..."
              : "مثال: عندي فرعين في مدينة نصر والتجمع، بنشتغل من 10 لـ10، د. أحمد بيقدم ليزر وإزالة شعر، وسعر الجلسة 1500 جنيه ومدتها ساعة..."
          }
        />
        <div className="flex flex-wrap gap-2">
          <SubmitButton
            label={pending ? "Tia بتفكر..." : terminal ? "ابدأ خطة جديدة" : "إرسال لـ Tia"}
            mode="chat"
          />
          {!terminal && response?.requires_confirmation && (
            <SubmitButton label="تأكيد وتنفيذ الخطة" mode="confirm" />
          )}
          {!terminal && response && (
            <SubmitButton label="إلغاء الخطة" mode="cancel" secondary />
          )}
          {pending && <LoaderCircle className="animate-spin text-teal-700" />}
        </div>
      </form>
    </section>
  );
}
