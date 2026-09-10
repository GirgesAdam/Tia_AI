import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ClinicKnowledgeEntry } from "@/lib/clinic-knowledge-base-types";
import type { ClinicSetupV2Snapshot } from "@/lib/clinic-setup-v2-types";
import { cn } from "@/lib/utils";

import {
  createKnowledgeEntryFormAction,
  deleteKnowledgeEntryFormAction,
  saveBookingPolicyFormAction,
  saveClinicHoursFormAction,
  saveClinicProfileFormAction,
  updateKnowledgeEntryFormAction,
} from "./clinic-settings-actions";

const DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"];
const DEVICES = [
  { key: "candela_gentle", name: "Candela Gentle" },
  { key: "prime_lase", name: "Prime Lase" },
];

function Field({ label, name, defaultValue, type = "text" }: { label: string; name: string; defaultValue?: string | number | null; type?: string }) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      <span>{label}</span>
      <Input name={name} type={type} defaultValue={defaultValue ?? ""} />
    </label>
  );
}

function KnowledgeEdit({ entry }: { entry: ClinicKnowledgeEntry }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{entry.title}</CardTitle>
        <CardDescription>
          {entry.scope_type === "clinic" ? "معلومة عامة عن العيادة" : entry.scope_type === "service" ? `خدمة: ${entry.service_name ?? "—"}` : `جهاز: ${entry.device_name ?? entry.device_key ?? "—"}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form action={updateKnowledgeEntryFormAction} className="space-y-3">
          <input type="hidden" name="id" value={entry.id} />
          <input type="hidden" name="scope_type" value={entry.scope_type} />
          {entry.service_id ? <input type="hidden" name="service_id" value={entry.service_id} /> : null}
          {entry.device_key ? <input type="hidden" name="device_key" value={entry.device_key} /> : null}
          <Field label="العنوان" name="title" defaultValue={entry.title} />
          <label className="grid gap-1 text-sm font-medium">
            <span>المعلومة التي يمكن لـ Tia شرحها للعميل</span>
            <textarea name="content" defaultValue={entry.content} rows={4} className="min-h-24 rounded-md border bg-background px-3 py-2 text-sm" />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="is_active" defaultChecked={entry.is_active} /> مفعّلة</label>
            <Button type="submit" size="sm">حفظ</Button>
          </div>
        </form>
        <form action={deleteKnowledgeEntryFormAction}>
          <input type="hidden" name="id" value={entry.id} />
          <Button type="submit" variant="outline" size="sm">حذف المعلومة</Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function ClinicSettingsPanel({ setup, knowledge }: { setup: ClinicSetupV2Snapshot; knowledge: ClinicKnowledgeEntry[] }) {
  const byDay = new Map(setup.clinic_hours.map((row) => [row.weekday, row]));
  const policy = setup.booking_policy;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle>بيانات العيادة</CardTitle>
          <CardDescription>المعلومات الأساسية التي تمثل العيادة. إدارة الخدمات والدكاترة أصبحت في صفحاتها المخصصة.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={saveClinicProfileFormAction} className="grid gap-4 md:grid-cols-2">
            <Field label="اسم العيادة" name="name" defaultValue={setup.clinic.name} />
            <Field label="رقم العيادة" name="phone" defaultValue={setup.clinic.phone} />
            <Field label="المدينة" name="city" defaultValue={setup.clinic.city} />
            <Field label="العنوان" name="address" defaultValue={setup.clinic.address} />
            <div className="md:col-span-2"><Button type="submit">حفظ بيانات العيادة</Button></div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>مواعيد الحجز في العيادة</CardTitle>
          <CardDescription>وقت النهاية هو آخر وقت يمكن أن يبدأ فيه حجز، وليس الوقت الذي يجب أن تنتهي فيه الجلسة. مثال: لو آخر وقت 10:00 م، يمكن لجلسة مدتها ساعة أن تبدأ 10:00 وتنتهي 11:00.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={saveClinicHoursFormAction} className="space-y-3">
            {DAYS.map((day, weekday) => {
              const row = byDay.get(weekday);
              return (
                <div key={day} className="grid items-end gap-3 rounded-lg border p-3 sm:grid-cols-[130px_1fr_1fr]">
                  <label className="flex h-10 items-center gap-2 text-sm font-medium"><input type="checkbox" name={`enabled_${weekday}`} defaultChecked={Boolean(row)} /> {day}</label>
                  <Field label="أول وقت بدء حجز" name={`start_${weekday}`} type="time" defaultValue={row?.start_time ?? "10:00"} />
                  <Field label="آخر وقت بدء حجز" name={`end_${weekday}`} type="time" defaultValue={row?.end_time ?? "22:00"} />
                </div>
              );
            })}
            <Button type="submit">حفظ مواعيد الحجز</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>سياسة الحجز</CardTitle>
          <CardDescription>قواعد تشغيلية يستخدمها محرك الحجز نفسه. مدة الجلسة والـbuffers ما زالت تمنع أي تعارض، لكن لا تمنع جلسة من الامتداد بعد آخر وقت بدء مسموح.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={saveBookingPolicyFormAction} className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Field label="فاصل مواعيد البداية (دقيقة)" name="slot_interval_minutes" type="number" defaultValue={policy.slot_interval_minutes} />
            <Field label="أقل مهلة قبل الحجز (دقيقة)" name="minimum_notice_minutes" type="number" defaultValue={policy.minimum_notice_minutes} />
            <Field label="مدى الحجز للأمام (يوم)" name="booking_horizon_days" type="number" defaultValue={policy.booking_horizon_days} />
            <Field label="مهلة الإلغاء (دقيقة)" name="cancellation_notice_minutes" type="number" defaultValue={policy.cancellation_notice_minutes} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="allow_same_day_booking" defaultChecked={policy.allow_same_day_booking} /> السماح بالحجز في نفس اليوم</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="require_confirmation" defaultChecked={policy.require_confirmation} /> الحجز يحتاج تأكيد</label>
            <div className="lg:col-span-4"><Button type="submit">حفظ سياسة الحجز</Button></div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Knowledge Base الخاصة بـ Tia</CardTitle>
          <CardDescription>اكتب معلومات شرح ومزايا وأسئلة شائعة. Tia تسترجع فقط المعلومات المرتبطة بالسؤال؛ الأسعار والمدد والمواعيد والمدفوعات تظل من البيانات التشغيلية ولا يمكن لهذه النصوص أن تستبدلها.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="rounded-lg border bg-muted/30 p-4 text-sm leading-6">
            استخدمها مثلًا لشرح طبيعة جلسة، ما الذي يميز جهاز Candela أو Prime Lase، أو معلومات عامة عن العيادة. لا تستخدمها لتسجيل سعر أو مدة أو availability لأن هذه القيم لها مصدر رسمي آخر في Tia.
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <form action={createKnowledgeEntryFormAction} className="space-y-3 rounded-lg border p-4">
              <input type="hidden" name="scope_type" value="clinic" /><input type="hidden" name="is_active" value="on" />
              <h3 className="font-semibold">معلومة عن العيادة</h3>
              <Field label="العنوان" name="title" />
              <textarea name="content" required rows={5} placeholder="مثال: ما الذي يميز تجربة العيادة..." className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
              <Button type="submit" size="sm">إضافة</Button>
            </form>

            <form action={createKnowledgeEntryFormAction} className="space-y-3 rounded-lg border p-4">
              <input type="hidden" name="scope_type" value="service" /><input type="hidden" name="is_active" value="on" />
              <h3 className="font-semibold">شرح خدمة</h3>
              <select name="service_id" required className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                <option value="">اختر الخدمة</option>{setup.services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
              </select>
              <Field label="العنوان" name="title" />
              <textarea name="content" required rows={4} placeholder="شرح أو مزايا أو سؤال شائع عن الخدمة" className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
              <Button type="submit" size="sm">إضافة</Button>
            </form>

            <form action={createKnowledgeEntryFormAction} className="space-y-3 rounded-lg border p-4">
              <input type="hidden" name="scope_type" value="laser_device" /><input type="hidden" name="is_active" value="on" />
              <h3 className="font-semibold">معلومة عن جهاز ليزر</h3>
              <select name="device_key" required className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                {DEVICES.map((device) => <option key={device.key} value={device.key}>{device.name}</option>)}
              </select>
              <Field label="العنوان" name="title" />
              <textarea name="content" required rows={4} placeholder="مزايا الجهاز أو الفرق الذي يمكن للعميل السؤال عنه" className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
              <Button type="submit" size="sm">إضافة</Button>
            </form>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">{knowledge.map((entry) => <KnowledgeEdit key={entry.id} entry={entry} />)}</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>مصادر البيانات التشغيلية</CardTitle><CardDescription>الإعدادات دي اتفصلت عشان كل نوع بيانات يبقى له مصدر واحد واضح.</CardDescription></CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Link href="/services" className={cn(buttonVariants({ variant: "outline" }))}>إدارة الخدمات والأسعار</Link>
          <Link href="/doctors" className={cn(buttonVariants({ variant: "outline" }))}>إدارة الدكاترة ومواعيدهم</Link>
          <Link href="/setup/integration" className={cn(buttonVariants())}>ربط أو استيراد البيانات القديمة</Link>
        </CardContent>
      </Card>
    </div>
  );
}
