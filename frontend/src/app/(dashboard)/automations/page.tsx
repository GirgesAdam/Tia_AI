import { CircleAlert, Clock3, Workflow } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/format";
import { labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { AutomationJob, AutomationOperationsOverview, AutomationRule } from "@/lib/types";
import { cancelAutomationJob, retryAutomationJob, saveAutomationTemplates, toggleAutomation } from "./actions";

const names: Record<string, string> = {
  booking_confirmation: "تأكيد الحجز",
  appointment_reminder_6h: "تذكير قبل الموعد",
  appointment_reminder_24h: "تذكير قبل 24 ساعة",
  appointment_reminder_2h: "تذكير قبل ساعتين",
  post_visit_followup: "متابعة بعد الزيارة",
  no_show_followup: "متابعة عدم الحضور",
};

const descriptions: Record<string, string> = {
  booking_confirmation: "ترسل رسالة تأكيد تلقائيًا بعد تسجيل الحجز.",
  appointment_reminder_6h: "تذكّر العميل بالموعد قبل 6 ساعات للمساعدة في تقليل عدم الحضور.",
  post_visit_followup: "تتابع مع العميل بعد الزيارة للاطمئنان واستكمال الخدمة عند الحاجة.",
  no_show_followup: "تتواصل مع العميل بعد عدم الحضور للمساعدة في إعادة الحجز.",
};

const visibleProductRuleKeys = new Set(["booking_confirmation", "appointment_reminder_6h", "post_visit_followup"]);

function attentionLabel(job: AutomationJob): string | null {
  if (job.attention_reason === "execution_failed") return "لم تكتمل العملية تلقائيًا";
  if (job.attention_reason === "delivery_failed") return "تعذر إرسال الرسالة";
  if (job.attention_reason === "stuck_processing") return "استغرق التنفيذ وقتًا أطول من المعتاد";
  return null;
}

function jobKindLabel(job: AutomationJob) {
  return job.job_kind === "crm_follow_up" ? "متابعة عميل" : "رسالة مرتبطة بموعد";
}

function variantNames(rule: AutomationRule): string[] {
  const raw = rule.config_json?.template_variants;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return "";
      return String((item as { name?: unknown }).name || "").trim();
    })
    .filter(Boolean);
}

function variablesHint(rule: AutomationRule): string {
  if (rule.key === "appointment_reminder_6h") {
    return "يجب أن تستخدم القوالب البديلة نفس بيانات الاسم والخدمة والوقت والفرع الموجودة في القالب الأساسي.";
  }
  if (rule.key === "post_visit_followup") {
    return "يجب أن تستخدم القوالب البديلة نفس بيانات الاسم والخدمة وتاريخ الجلسة الموجودة في القالب الأساسي.";
  }
  return "استخدم نفس البيانات والمتغيرات الموجودة في القالب الأساسي.";
}

function automationWarning(state: AutomationOperationsOverview["worker_state"]) {
  if (state === "stale") return "محرك تنفيذ الأتمتة غير متصل حاليًا، لذلك لن تُرسل الرسائل التلقائية حتى يعود الاتصال.";
  if (state === "missing") return "لم يتم ربط محرك تنفيذ الأتمتة بعد، لذلك لن تُرسل الرسائل التلقائية حتى يكتمل إعداد التشغيل.";
  return null;
}

export default async function AutomationsPage() {
  const [rawRules, jobs, overview, ctx] = await Promise.all([
    tiaRequest<AutomationRule[]>("/automations/rules"),
    tiaRequest<AutomationJob[]>("/automations/jobs?limit=50"),
    tiaRequest<AutomationOperationsOverview>("/automations/overview"),
    getAppContext(),
  ]);
  const rules = rawRules.filter((rule) => visibleProductRuleKeys.has(rule.key));
  const attentionJobs = jobs.filter((job) => Boolean(attentionLabel(job)));
  const recentJobs = jobs.slice(0, 12);
  const warning = automationWarning(overview.worker_state);

  return (
    <>
      <PageHeader
        title="الأتمتة"
        description="حدد الرسائل والمتابعات التي تنفذها Tia تلقائيًا، وراجع فقط الحالات التي تحتاج تدخلًا من الفريق."
      />

      {warning && (
        <div className="mb-5 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <CircleAlert size={18} className="mt-0.5 shrink-0" />
          <div>
            <b>تحتاج مراجعة</b>
            <p className="mt-1 leading-6">{warning}</p>
            {overview.worker_last_seen_at && (
              <p className="mt-1 text-xs">آخر اتصال بمحرك التنفيذ: {formatDateTime(overview.worker_last_seen_at)}</p>
            )}
          </div>
        </div>
      )}

      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs font-semibold text-[var(--muted)]">القواعد المفعّلة</div>
            <div className="mt-1 text-2xl font-black text-slate-950">{overview.enabled_rules}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs font-semibold text-[var(--muted)]">تحتاج تدخلًا</div>
            <div className="mt-1 text-2xl font-black text-slate-950">{overview.attention_count}</div>
            <div className="mt-1 text-[11px] text-[var(--muted)]">تظهر التفاصيل فقط عند وجود مشكلة</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs font-semibold text-[var(--muted)]">التنفيذ التالي</div>
            <div className="mt-1 font-bold text-slate-900">{overview.next_job_at ? formatDateTime(overview.next_job_at) : "لا يوجد إجراء قريب"}</div>
          </CardContent>
        </Card>
      </div>

      <div className="mb-3">
        <h2 className="text-lg font-black text-slate-950">الرسائل والمتابعات التلقائية</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">فعّل ما تحتاجه فقط. كل قاعدة تعمل بشكل مستقل ويمكن إيقافها في أي وقت.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {rules.map((rule) => {
          const variants = variantNames(rule);
          return (
            <Card key={rule.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <b className="text-slate-950">{names[rule.key] || rule.name}</b>
                      <Badge tone={rule.enabled ? "green" : "gray"}>{rule.enabled ? "مفعّلة" : "متوقفة"}</Badge>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{descriptions[rule.key] || "تنفذ إجراءً تلقائيًا عند تحقق شروط هذه القاعدة."}</p>
                    <div className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                      <Clock3 size={13} /> واتساب
                    </div>
                  </div>

                  {ctx.workspace.role === "admin" && (
                    <form action={toggleAutomation}>
                      <input type="hidden" name="rule_id" value={rule.id} />
                      <input type="hidden" name="enabled" value={String(!rule.enabled)} />
                      <Button size="sm" variant={rule.enabled ? "outline" : "default"}>
                        {rule.enabled ? "إيقاف" : "تفعيل"}
                      </Button>
                    </form>
                  )}
                </div>

                {ctx.workspace.role === "admin" && (
                  <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                    <summary className="cursor-pointer text-xs font-bold text-slate-600">إعدادات واتساب المتقدمة</summary>
                    <form action={saveAutomationTemplates} className="mt-3 space-y-3">
                      <input type="hidden" name="rule_id" value={rule.id} />
                      <p className="text-[11px] leading-5 text-[var(--muted)]">{variablesHint(rule)}</p>
                      <div className="grid gap-3 sm:grid-cols-[1fr_110px]">
                        <label className="text-xs font-bold text-slate-700">
                          اسم قالب واتساب
                          <Input name="template_name" defaultValue={rule.template_name} required dir="ltr" className="mt-1" />
                        </label>
                        <label className="text-xs font-bold text-slate-700">
                          اللغة
                          <Input name="template_language" defaultValue={rule.template_language} required dir="ltr" className="mt-1" placeholder="ar" />
                        </label>
                      </div>
                      <label className="block text-xs font-bold text-slate-700">
                        قوالب بديلة - اختياري
                        <Textarea
                          name="template_variants"
                          defaultValue={variants.join("\n")}
                          dir="ltr"
                          placeholder={"اسم قالب إضافي في كل سطر"}
                          className="mt-1 min-h-24 text-xs"
                        />
                      </label>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-[11px] text-[var(--muted)]">يمكن إضافة حتى 20 قالبًا بديلًا.</span>
                        <Button type="submit" size="sm" variant="outline">حفظ الإعدادات</Button>
                      </div>
                    </form>
                  </details>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {attentionJobs.length > 0 && (
        <Card className="mt-6 border-amber-200">
          <CardHeader>
            <CardTitle>حالات تحتاج تدخلًا</CardTitle>
            <p className="text-xs leading-5 text-[var(--muted)]">هذه العمليات لم تكتمل تلقائيًا ويمكن للمدير إعادة المحاولة أو إلغاؤها.</p>
          </CardHeader>
          <CardContent className="space-y-3">
            {attentionJobs.map((job) => {
              const attention = attentionLabel(job);
              const canRetry = job.attention_reason === "execution_failed" || job.attention_reason === "delivery_failed";
              const canCancel = job.status === "queued" || job.status === "failed" || (job.status === "dispatched" && job.dispatch_status === "queued");
              return (
                <div key={job.id} className="flex flex-col gap-3 rounded-xl bg-amber-50/70 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <b className="text-sm text-slate-950">{jobKindLabel(job)}</b>
                      <Badge tone={toneForStatus(job.status)}>{labelForStatus(job.status)}</Badge>
                    </div>
                    <p className="mt-1 text-xs font-semibold text-amber-800">{attention}</p>
                    <div className="mt-1 text-xs text-[var(--muted)]">{formatDateTime(job.scheduled_for)}</div>
                  </div>
                  {ctx.workspace.role === "admin" && (canRetry || canCancel) && (
                    <div className="flex gap-2">
                      {canRetry && (
                        <form action={retryAutomationJob}>
                          <input type="hidden" name="job_id" value={job.id} />
                          <Button size="sm" variant="outline">إعادة المحاولة</Button>
                        </form>
                      )}
                      {canCancel && (
                        <form action={cancelAutomationJob}>
                          <input type="hidden" name="job_id" value={job.id} />
                          <Button size="sm" variant="ghost">إلغاء</Button>
                        </form>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <details className="mt-6 rounded-2xl border border-[var(--border)] bg-white p-4">
        <summary className="cursor-pointer text-sm font-bold text-slate-800">سجل النشاط الأخير</summary>
        <div className="mt-4">
          {recentJobs.length ? (
            <div className="divide-y divide-[var(--border)]">
              {recentJobs.map((job) => (
                <div key={job.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <b className="text-sm">{jobKindLabel(job)}</b>
                    <div className="mt-1 text-xs text-[var(--muted)]">{formatDateTime(job.scheduled_for)}</div>
                  </div>
                  <Badge tone={toneForStatus(job.status)}>{labelForStatus(job.status)}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={Workflow} title="لا يوجد نشاط بعد" description="سيظهر هنا آخر نشاط للرسائل والمتابعات التلقائية." />
          )}
        </div>
      </details>
    </>
  );
}
