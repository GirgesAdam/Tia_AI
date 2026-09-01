import Link from "next/link";
import { ArrowRight, CalendarClock } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import { tiaRequest } from "@/lib/tia/api";
import type { AppointmentOperationsDetail, AvailabilityResponse } from "@/lib/types";
import { rescheduleAppointment } from "../actions";

function localDateKey(value: string, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(value));
  const map = new Map(parts.map((part) => [part.type, part.value]));
  return `${map.get("year")}-${map.get("month")}-${map.get("day")}`;
}

export default async function RescheduleAppointmentPage({
  params,
  searchParams,
}: {
  params: Promise<{ appointmentId: string }>;
  searchParams: Promise<{ date?: string }>;
}) {
  const { appointmentId } = await params;
  const { date } = await searchParams;
  const detail = await tiaRequest<AppointmentOperationsDetail>(`/booking/appointments/${appointmentId}/operations`);
  const selectedDate = date && date.length === 10 ? date : localDateKey(detail.appointment.start_at, detail.timezone);
  const query = new URLSearchParams({
    branch_id: detail.appointment.branch_id,
    service_id: detail.appointment.service_id,
    doctor_id: detail.appointment.doctor_id,
    date: selectedDate,
  });
  const availability = detail.allowed_actions.includes("reschedule")
    ? await tiaRequest<AvailabilityResponse>(`/booking/availability?${query.toString()}`)
    : { date: selectedDate, timezone: detail.timezone, slots: [] };

  return <>
    <PageHeader
      title="تغيير الموعد"
      description={`${detail.patient.name} · ${detail.service.name} · ${detail.doctor.name}`}
      action={<Link href={`/appointments/${appointmentId}`} className={buttonVariants({ variant: "outline" })}><ArrowRight size={15}/>الرجوع للموعد</Link>}
    />
    <Card>
      <CardHeader><CardTitle>اختار يوم جديد</CardTitle></CardHeader>
      <CardContent>
        <form method="GET" className="flex flex-wrap items-end gap-2">
          <label className="text-sm font-bold">التاريخ<input type="date" name="date" defaultValue={selectedDate} className="mt-2 block h-10 rounded-xl border border-[var(--border)] px-3 font-normal"/></label>
          <Button type="submit" variant="outline">عرض المواعيد</Button>
        </form>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {availability.slots.map((slot) => <form key={slot.start_at} action={rescheduleAppointment} className="rounded-xl border border-[var(--border)] p-4">
            <input type="hidden" name="appointment_id" value={appointmentId}/><input type="hidden" name="start_at" value={slot.start_at}/>
            <div className="flex items-center gap-2 text-sm font-black"><CalendarClock size={15}/>{formatDateTime(slot.start_at)}</div>
            <div className="mt-1 text-xs text-[var(--muted)]">{availability.timezone}</div>
            <Button type="submit" size="sm" className="mt-3 w-full">اختيار الموعد</Button>
          </form>)}
        </div>
        {!availability.slots.length && <div className="mt-6 rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--muted)]">مفيش مواعيد متاحة مع نفس الدكتور والفرع في اليوم ده.</div>}
      </CardContent>
    </Card>
  </>;
}
