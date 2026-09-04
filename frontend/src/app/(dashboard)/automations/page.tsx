import { CircleAlert, Clock3, Workflow } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";
import { labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { AutomationJob, AutomationOperationsOverview, AutomationRule } from "@/lib/types";
import { cancelAutomationJob, retryAutomationJob, saveAutomationTiming, toggleAutomation } from "./actions";

const names: Record<string, string> = {
  booking_confirmation: "تأكيد الحجز",
  appointment_reminder_6h: "تذكير قبل الموعد",
  post_visit_followup: "متابعة بعد الزيارة",
  cancellation_recovery: "استرجاع الحجوزات الملغاة",
  lead_not_booked_followup: "متابعة العميل اللي ماحجزش",
};

const descriptions: Record<string, string> = {
  booking_confirmation: "ترسل رسالة تأكيد تلقائيًا بعد تسجيل الحجز.",
  appointment_reminder_6h: "تذكّر العميل بالموعد في التوقيت الذي تحدده العيادة.",
  post_visit_followup: "رسالة واحدة للاطمئنان، عرض المساعدة أو حجز الجلسة التالية، وطلب التقييم.",
  cancellation_recovery: "اختياري: تتواصل مع العميل بعد إلغاء الموعد وتعرض عليه ترتيب موعد جديد.",
  lead_not_booked_followup: "اختياري: تتابع العميل المهتم لو لسه ماحجزش وتساعده يكمل الحجز.",
};

const visibleProductRuleKeys = new Set([
  "booking_confirmation",
  "appointment_reminder_6h",
  "post_visit_followup",
  "cancellation_recovery",
  "lead_not_booked_followup",
]);

const timingRuleKeys = new Set(["appointment_reminder_6h", "post_visit_followup", "cancellation_recovery", "lead_not_booked_followup"]);

function attentionLabel(job: AutomationJob): string | null {
  if (job.attention_reason === "execution_failed") return "لم تكتمل العملية تلقائيًا";
  if (job.attention_reason === "delivery_failed") return "تعذر إرسال الرسالة";
  if (job.attention_reason === "stuck_processing") return "استغرق التنفيذ وقتًا أطول من المعتاد";
  return null;
}

function jobKindLabel(job: AutomationJob) {
  return job.job_kind === "crm_follow_up" ? "متابعة عميل" : "رسالة مرتبطة بموعد";
}

function timingParts(rule: AutomationRule): { value: number; unit: "minutes" | "hours" | "days" } {
  const minutes = Math.abs(rule.offset_minutes);
  if (minutes >= 1440 && minutes % 1440 === 0) return { value: minutes / 1440, unit: "days" };
  if (minutes >= 60 && minutes % 60 === 0) return { value: minutes / 60, unit: "hours" };
  return { value: minutes, unit: "minutes" };
}

function timingLabel(rule: AutomationRule): string {
  if (rule.trigger_kind === "before_appointment") return "أرسل قبل الموعد بـ";
  if (rule.trigger_kind === "after_completed") return "أرسل بعد انتهاء الزيارة بـ";
  if (rule.trigger_kind === "after_no_show") return "أرسل بعد عدم الحضور بـ";
  if (rule.trigger_kind === "after_cancelled") return "أرسل بعد إلغاء الموعد بـ";
  if (rule.trigger_kind === "after_lead_activity") return "أرسل بعد آخر تواصل بـ";
  return "التوقيت";
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
        description="فعّل فقط المتابعات التي تحتاجها العيادة وحدد توقيتها بدون إعداد workflows معقدة."
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
        <p className="mt-1 text-sm text-[var(--muted)]">كل ميزة مستقلة. المزايا غير الضرورية يمكن تركها متوقفة وتفعيلها عند الحاجة.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {rules.map((rule) => {
          const timing = timingParts(rule);
          const hasTiming = timingRuleKeys.has(rule.key);
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

                {ctx.workspace.role === "admin" && hasTiming && (
                  <form action={saveAutomationTiming} className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                    <input type="hidden" name="rule_id" value={rule.id} />
                    <input type="hidden" name="trigger_kind" value={rule.trigger_kind} />
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                      <label className="min-w-0 flex-1 text-xs font-bold text-slate-700">
                        {timingLabel(rule)}
                        <Input
                          name="timing_value"
                          type="number"
                          min="0"
                          max="10080"
                          step="1"
                          defaultValue={timing.value}
                          required
                          className="mt-1"
                        />
                      </label>
                      <label className="text-xs font-bold text-slate-700">
                        الوحدة
                        <select
                          name="timing_unit"
                          defaultValue={timing.unit}
                          className="mt-1 h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
                        >
                          <option value="minutes">دقيقة</option>
                          <option value="hours">ساعة</option>
                          <option value="days">يوم</option>
                        </select>
                      </label>
                      <Button type="submit" size="sm" variant="outline">حفظ التوقيت</Button>
                    </div>
                    <p className="mt-2 text-[11px] leading-5 text-[var(--muted)]">الحد الأقصى الحالي 7 أيام حتى تظل المتابعات قريبة من الحدث ومفهومة.</p>
                  </form>
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
