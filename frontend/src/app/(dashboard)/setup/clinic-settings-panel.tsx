import { Download, History } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ClinicSetupV2Snapshot, HistoricalBatch } from "@/lib/clinic-setup-v2-types";

import {
  saveClinicHoursFormAction,
  saveClinicProfileFormAction,
  saveKnowledgeTextFormAction,
} from "./clinic-settings-actions";
import { HistoricalImportUploader } from "./integration/history-uploader";

const DAYS = [
  { weekday: 5, label: "السبت" },
  { weekday: 6, label: "الأحد" },
  { weekday: 0, label: "الإثنين" },
  { weekday: 1, label: "الثلاثاء" },
  { weekday: 2, label: "الأربعاء" },
  { weekday: 3, label: "الخميس" },
  { weekday: 4, label: "الجمعة" },
] as const;

const KNOWLEDGE_EXAMPLE = `مثال مناسب — عدّله حسب عيادتك:
العيادة متخصصة في الليزر والعناية بالبشرة. نقدم إزالة الشعر بالليزر لمناطق مختلفة، واستشارات جلدية وليزر، وجلسات عناية بالبشرة مثل الهيدرافيشل والفراكشنال حسب احتياج الحالة.

في إزالة الشعر نستخدم Prime Lase وCandela Gentle. مفيش جهاز أفضل لكل الناس؛ الجهاز الأنسب يختلف حسب نوع البشرة والشعر والمنطقة وتقييم المختص. اكتب هنا أي فرق أو ميزة فعلية خاصة بالأجهزة الموجودة عندك لو حابب Tia تشرحها للعملاء.

الهيدرافيشل جلسة عناية هدفها تنظيف وترطيب البشرة وتحسين مظهرها. قبل جلسة إزالة الشعر يفضّل الحلاقة بالموس وعدم استخدام الشمع أو الحلاوة، وأي تعليمات خاصة بالحالة يحددها المختص.

اكتب هنا كمان السياسات أو الأسئلة الشائعة المهمة للعميل. ما تكتبش أسعار أو مدد جلسات أو مواعيد متاحة أو أرصدة باقات؛ Tia بتاخد المعلومات دي تلقائيًا من بيانات العيادة.`;

const statusLabel: Record<HistoricalBatch["status"], string> = {
  preview_ready: "تم الفحص",
  importing: "جاري الاستيراد",
  imported: "مكتمل",
  failed: "لم يكتمل",
};

function Field({ label, name, defaultValue, type = "text" }: { label: string; name: string; defaultValue?: string | number | null; type?: string }) {
  return (
    <label className="grid gap-1.5 text-sm font-medium">
      <span>{label}</span>
      <Input name={name} type={type} defaultValue={defaultValue ?? ""} />
    </label>
  );
}

export function ClinicSettingsPanel({
  setup,
  knowledgeText,
  historicalBatches,
  activeBatch,
}: {
  setup: ClinicSetupV2Snapshot;
  knowledgeText: string;
  historicalBatches: HistoricalBatch[];
  activeBatch: HistoricalBatch | null;
}) {
  const byDay = new Map(setup.clinic_hours.map((row) => [row.weekday, row]));

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle>بيانات العيادة</CardTitle>
          <CardDescription>البيانات الأساسية التي تظهر وتمثل العيادة داخل Tia.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={saveClinicProfileFormAction} className="grid gap-4 md:grid-cols-2">
            <Field label="اسم العيادة" name="name" defaultValue={setup.clinic.name} />
            <Field label="رقم الهاتف" name="phone" defaultValue={setup.clinic.phone} />
            <Field label="المدينة" name="city" defaultValue={setup.clinic.city} />
            <Field label="العنوان" name="address" defaultValue={setup.clinic.address} />
            <div className="md:col-span-2"><Button type="submit">حفظ بيانات العيادة</Button></div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>مواعيد عمل العيادة</CardTitle>
          <CardDescription>فعّل الأيام التي تعمل فيها العيادة وحدد بداية ونهاية العمل لكل يوم.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={saveClinicHoursFormAction} className="space-y-3">
            {DAYS.map(({ weekday, label }) => {
              const row = byDay.get(weekday);
              return (
                <div key={weekday} className="grid items-end gap-3 rounded-xl border border-[var(--border)] p-3 sm:grid-cols-[130px_1fr_1fr] sm:items-end">
                  <label className="flex h-10 items-center gap-2 text-sm font-bold">
                    <input type="checkbox" name={`enabled_${weekday}`} defaultChecked={Boolean(row)} />
                    {label}
                  </label>
                  <Field label="من" name={`start_${weekday}`} type="time" defaultValue={row?.start_time ?? "10:00"} />
                  <Field label="إلى" name={`end_${weekday}`} type="time" defaultValue={row?.end_time ?? "22:00"} />
                </div>
              );
            })}
            <Button type="submit">حفظ مواعيد العمل</Button>
          </form>
        </CardContent>
      </Card>

      <Card id="tia-knowledge">
        <CardHeader>
          <CardTitle>معلومات Tia</CardTitle>
          <CardDescription>اكتب هنا فقط المعلومات التفسيرية التي تريد Tia أن تعرفها وتشرحها للعملاء: نبذة العيادة، شرح الخدمات، الفرق بين الأجهزة، التعليمات والسياسات والأسئلة الشائعة.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={saveKnowledgeTextFormAction} className="space-y-4">
            <textarea
              name="content"
              defaultValue={knowledgeText}
              rows={14}
              maxLength={6000}
              placeholder={KNOWLEDGE_EXAMPLE}
              className="min-h-64 w-full resize-y rounded-xl border border-[var(--border)] bg-background px-4 py-3 text-sm leading-7 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
            />
            <p className="text-xs leading-5 text-[var(--muted)]">الأسعار والمدد والمواعيد والمدفوعات والباقات لا تُكتب هنا؛ تظل مأخوذة من بيانات Tia التشغيلية، والنص هنا هو مصدر الشرح الحر الوحيد للرد على استفسارات العملاء.</p>
            <Button type="submit">حفظ معلومات Tia</Button>
          </form>
        </CardContent>
      </Card>

      <Card id="historical-data">
        <CardHeader>
          <CardTitle>البيانات القديمة</CardTitle>
          <CardDescription>لو عندك بيانات من النظام السابق، ارفعها هنا لنقل العملاء والمواعيد والمدفوعات والباقات إلى Tia.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/70 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <b className="text-sm">قالب الاستيراد</b>
              <p className="mt-1 text-xs leading-5 text-[var(--muted)]">استخدم قالب Tia الثابت لو محتاج تجهيز البيانات قبل الرفع.</p>
            </div>
            <a href="/api/clinic-history-template" className={buttonVariants({ variant: "outline" })}><Download size={16} /> تحميل القالب</a>
          </div>

          <HistoricalImportUploader initialBatch={activeBatch} />

          <div className="rounded-xl border border-[var(--border)] p-4">
            <div className="mb-3 flex items-center gap-2"><History size={17} /><b className="text-sm">آخر عمليات الاستيراد</b></div>
            {historicalBatches.length ? (
              <div className="space-y-2">
                {historicalBatches.map((batch) => (
                  <div key={batch.batch_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                    <div>
                      <div className="text-sm font-bold">{batch.source_name}</div>
                      <div className="mt-1 text-xs text-[var(--muted)]">{batch.mode === "append" ? "إضافة للبيانات الحالية" : "استبدال الاستيرادات السابقة"}</div>
                    </div>
                    <Badge tone={batch.status === "imported" ? "green" : batch.status === "failed" ? "red" : "yellow"}>{statusLabel[batch.status]}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">لا توجد عمليات استيراد سابقة.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
