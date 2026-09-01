import Link from "next/link";
import { BookOpenCheck, CalendarDays, ContactRound, Settings2 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { WeeklyScheduleTable } from "@/components/weekly-schedule-table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { formatDateTime, formatMoney } from "@/lib/format";
import type { AgentKnowledgeSnapshot } from "@/lib/agent-knowledge-types";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import { AgentKnowledgeAssistant } from "./assistant";

function DataTable({ title, count, headers, rows }: { title: string; count: number; headers: string[]; rows: React.ReactNode[][] }) {
  return (
    <details open className="rounded-2xl border border-[var(--border)] bg-white">
      <summary className="cursor-pointer list-none px-4 py-3 font-black"><span>{title}</span><Badge className="mr-2">{count}</Badge></summary>
      <div className="overflow-x-auto border-t border-[var(--border)]">
        <table className="w-full min-w-[760px] text-right text-xs">
          <thead className="bg-slate-50"><tr>{headers.map((header) => <th key={header} className="whitespace-nowrap px-3 py-3 font-black">{header}</th>)}</tr></thead>
          <tbody>{rows.length ? rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-slate-100">{row.map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-3 align-top">{cell}</td>)}</tr>
          )) : <tr><td colSpan={headers.length} className="px-3 py-6 text-center text-[var(--muted)]">لا توجد بيانات.</td></tr>}</tbody>
        </table>
      </div>
    </details>
  );
}

const paymentLabels: Record<string, string> = { unknown: "غير معروف", unpaid: "غير مدفوع", partial: "مدفوع جزئيًا", paid: "مدفوع", refunded: "مسترد" };
const methodLabels: Record<string, string> = { unknown: "غير معروف", cash: "كاش", card: "كارت", bank_transfer: "تحويل بنكي", wallet: "محفظة", other: "أخرى" };

export default async function AgentKnowledgePage() {
  const [knowledge, ctx] = await Promise.all([
    tiaRequest<AgentKnowledgeSnapshot>("/clinic/knowledge"),
    getAppContext(),
  ]);
  const admin = ctx.workspace.role === "admin";

  const branchScheduleRows = knowledge.branches.map((branch) => ({ key: branch.id, label: branch.name, hours: branch.working_hours }));
  const doctorScheduleRows = knowledge.doctors.flatMap((doctor) => doctor.schedules.map((schedule) => ({
    key: `${doctor.id}:${schedule.branch_id}`,
    label: doctor.name,
    secondary: schedule.branch_name,
    hours: schedule.working_hours,
  })));

  return (
    <>
      <PageHeader
        title="بيانات Tia"
        description="راجع المعلومات التي تعتمد عليها Tia عند الرد على العملاء وإدارة الحجز."
        action={<Link href="/setup" className={buttonVariants({ variant: "outline" })}><Settings2 size={17} /> إعدادات العيادة</Link>}
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["الخدمات", knowledge.services.length],
          ["الفروع", knowledge.branches.length],
          ["الدكاترة", knowledge.doctors.length],
          ["العملاء / الحجوزات", `${knowledge.patient_count} / ${knowledge.appointment_count}`],
        ].map(([label, value]) => <Card key={String(label)}><CardContent className="p-4"><div className="text-xs font-bold text-[var(--muted)]">{label}</div><div className="mt-1 text-2xl font-black">{String(value)}</div></CardContent></Card>)}
      </div>

      <AgentKnowledgeAssistant admin={admin} />

      {!admin && <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm">تقدر تشوف البيانات. التعديل بالشات متاح للـAdmin فقط.</div>}

      <div className="mt-6 space-y-5">
        <DataTable
          title="الخدمات"
          count={knowledge.services.length}
          headers={["الخدمة", "المدة", "السعر", "التصنيف", "الحالة"]}
          rows={knowledge.services.map((service) => [
            <div key="name"><b>{service.name}</b>{service.description && <div className="mt-1 max-w-md text-[var(--muted)]">{service.description}</div>}</div>,
            `${service.duration_minutes} دقيقة`,
            formatMoney(service.price_minor, service.currency),
            service.category || "—",
            <Badge key="status" tone={service.is_active ? "green" : "gray"}>{service.is_active ? "نشط" : "غير نشط"}</Badge>,
          ])}
        />

        <DataTable
          title="الفروع"
          count={knowledge.branches.length}
          headers={["الفرع", "المدينة", "العنوان", "الهاتف", "المنطقة الزمنية", "الحالة"]}
          rows={knowledge.branches.map((branch) => [branch.name, branch.city || "—", branch.address_line1 || "—", branch.phone || "—", branch.timezone || knowledge.workspace_timezone, <Badge key="status" tone={branch.is_active ? "green" : "gray"}>{branch.is_active ? "نشط" : "غير نشط"}</Badge>])}
        />

        <Card>
          <CardHeader><CardTitle>مواعيد عمل الفروع</CardTitle></CardHeader>
          <CardContent><WeeklyScheduleTable rows={branchScheduleRows} firstHeader="الفرع" /></CardContent>
        </Card>

        <DataTable
          title="الدكاترة والربط"
          count={knowledge.doctors.length}
          headers={["الدكتور", "التخصص", "الخدمات", "الفروع", "الهاتف", "الحجز"]}
          rows={knowledge.doctors.map((doctor) => [
            doctor.name,
            doctor.specialization || "—",
            doctor.services.map((item) => item.name).join("، ") || "—",
            doctor.branches.map((item) => `${item.name}${item.is_primary ? " (أساسي)" : ""}`).join("، ") || "—",
            doctor.phone || "—",
            doctor.booking_enabled ? "متاح" : "موقوف",
          ])}
        />

        <Card>
          <CardHeader><CardTitle>مواعيد عمل الدكاترة</CardTitle></CardHeader>
          <CardContent><WeeklyScheduleTable rows={doctorScheduleRows} firstHeader="الدكتور" secondHeader="الفرع" /></CardContent>
        </Card>

        {knowledge.booking_settings && (
          <DataTable
            title="إعدادات الحجز"
            count={1}
            headers={["تقسيم المواعيد", "أقل مهلة", "مدى الحجز", "مهلة الإلغاء", "نفس اليوم", "تأكيد مطلوب"]}
            rows={[[]].map(() => [
              `${knowledge.booking_settings!.slot_interval_minutes} دقيقة`,
              `${knowledge.booking_settings!.minimum_notice_minutes} دقيقة`,
              `${knowledge.booking_settings!.booking_horizon_days} يوم`,
              `${knowledge.booking_settings!.cancellation_notice_minutes} دقيقة`,
              knowledge.booking_settings!.allow_same_day_booking ? "نعم" : "لا",
              knowledge.booking_settings!.require_confirmation ? "نعم" : "لا",
            ])}
          />
        )}

        <details className="rounded-2xl border border-[var(--border)] bg-white">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 font-black"><span>العملاء</span><span className="flex items-center gap-2"><Badge>{knowledge.patient_count}</Badge><Link href="/patients" className="text-xs text-teal-700"><ContactRound size={15} className="inline" /> فتح صفحة العملاء</Link></span></summary>
          <div className="border-t border-[var(--border)] p-4">
            <DataTable title="بيانات العملاء" count={knowledge.patients.length} headers={["الاسم", "الموبايل", "الحالة", "المصدر"]} rows={knowledge.patients.map((patient) => [patient.name, patient.phone || "—", patient.status, patient.source])} />
          </div>
        </details>

        <details className="rounded-2xl border border-[var(--border)] bg-white">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 font-black"><span>الحجوزات الحالية</span><span className="flex items-center gap-2"><Badge>{knowledge.appointment_count}</Badge><Link href="/appointments" className="text-xs text-teal-700"><CalendarDays size={15} className="inline" /> فتح صفحة الحجوزات</Link></span></summary>
          <div className="border-t border-[var(--border)] p-4">
            <DataTable title="الحجوزات" count={knowledge.appointments.length} headers={["العميل", "الموبايل", "الخدمة", "الفرع", "الدكتور", "الموعد", "الحالة", "الدفع", "المدفوع", "الوسيلة"]} rows={knowledge.appointments.map((appointment) => [
              appointment.patient_name,
              appointment.patient_phone || "—",
              appointment.service_name,
              appointment.branch_name,
              appointment.doctor_name,
              formatDateTime(appointment.start_at),
              appointment.status,
              paymentLabels[appointment.payment_status] || appointment.payment_status,
              appointment.amount_paid_minor == null ? "—" : formatMoney(appointment.amount_paid_minor, "EGP"),
              methodLabels[appointment.payment_method] || appointment.payment_method,
            ])} />
          </div>
        </details>
      </div>

      <div className="mt-6 rounded-2xl border border-teal-200 bg-teal-50 p-4 text-sm leading-7 text-teal-950">
        <div className="flex items-start gap-3"><BookOpenCheck className="mt-1 shrink-0" size={20} /><div><b>هذه هي البيانات الحالية المستخدمة فعليًا.</b><div>أي تعديل يتم حفظه في إعدادات العيادة سيظهر هنا، وهو نفس المصدر الذي تعتمد عليه Tia أثناء العمل.</div></div></div>
      </div>
    </>
  );
}
