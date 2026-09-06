import Link from "next/link";
import { CalendarClock, ChevronLeft, Stethoscope } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FilterChip } from "@/components/ui/filter-chip";
import { formatDateTime, formatMoney } from "@/lib/format";
import { appointmentLabels, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { Appointment, AppointmentStatus, Doctor, Patient, Service, Staff } from "@/lib/types";
import { changeAppointmentStatus } from "./actions";

type SearchParams = { patient_id?: string; scope?: string; status?: string };
const scopes = [["today", "اليوم"], ["upcoming", "القادمة"], ["past", "السابقة"], ["all", "الكل"]] as const;
const statuses: Array<["" | AppointmentStatus, string]> = [
  ["", "كل الحالات"],
  ["pending", "قيد الانتظار"],
  ["confirmed", "مؤكد"],
  ["completed", "مكتمل"],
  ["no_show", "لم يحضر"],
  ["cancelled", "ملغي"],
  ["rescheduled", "تم تغيير الموعد"],
];

function hrefFor(current: SearchParams, key: keyof SearchParams, value: string) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(current)) if (v && k !== key) params.set(k, v);
  if (value) params.set(key, value);
  const query = params.toString();
  return query ? `/appointments?${query}` : "/appointments";
}

function bookingMethod(source: string) {
  return source === "ai" ? "Tia AI" : "الاستقبال";
}

function availableManualStatuses(appointment: Appointment, now: number): AppointmentStatus[] {
  const started = new Date(appointment.start_at).getTime() <= now;
  if (appointment.status === "pending") {
    return started ? ["completed", "no_show"] : ["confirmed", "cancelled"];
  }
  if (appointment.status === "confirmed") {
    return started ? ["completed", "no_show"] : ["cancelled"];
  }
  if ((appointment.status === "checked_in" || appointment.status === "in_progress") && started) {
    return ["completed", "no_show"];
  }
  return [];
}

function StatusControl({
  appointment,
  patientId,
  canOverrideCancellation,
  now,
}: {
  appointment: Appointment;
  patientId: string;
  canOverrideCancellation: boolean;
  now: number;
}) {
  const options = availableManualStatuses(appointment, now);
  if (!options.length) {
    return <Badge tone={toneForStatus(appointment.status)}>{appointmentLabels[appointment.status] || "غير محدد"}</Badge>;
  }

  return (
    <form action={changeAppointmentStatus} className="flex min-w-[170px] items-center gap-1.5">
      <input type="hidden" name="appointment_id" value={appointment.id} />
      <input type="hidden" name="patient_id" value={patientId} />
      <input type="hidden" name="can_override_cancellation" value={canOverrideCancellation ? "1" : "0"} />
      <select name="status" defaultValue="" required className="h-8 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700">
        <option value="" disabled>{appointmentLabels[appointment.status] || "الحالة الحالية"}</option>
        {options.map((value) => <option key={value} value={value}>{appointmentLabels[value] || value}</option>)}
      </select>
      <Button size="sm" variant="outline" className="h-8 px-2.5">حفظ</Button>
    </form>
  );
}

export default async function AppointmentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const raw = await searchParams;
  const patientId = raw.patient_id;
  const defaultScope = patientId ? "all" : "today";
  const scope = scopes.some(([value]) => value === raw.scope) ? raw.scope! : defaultScope;
  const status = statuses.some(([value]) => value === raw.status) ? raw.status || "" : "";
  const filters: SearchParams = { patient_id: patientId, scope, status };

  const query = new URLSearchParams({ limit: "200", scope });
  if (patientId) query.set("patient_id", patientId);
  if (status) query.set("status", status);

  const [appointments, patients, services, doctors, staff, ctx] = await Promise.all([
    tiaRequest<Appointment[]>(`/booking/appointments?${query.toString()}`),
    patientId
      ? tiaRequest<Patient>(`/crm/patients/${patientId}`).then((patient) => [patient])
      : tiaRequest<Patient[]>("/crm/patients?limit=100"),
    tiaRequest<Service[]>("/clinic/services"),
    tiaRequest<Doctor[]>("/clinic/doctors"),
    tiaRequest<Staff[]>("/clinic/staff"),
    getAppContext(),
  ]);

  const patientMap = new Map(patients.map((item) => [item.id, `${item.first_name} ${item.last_name || ""}`.trim()]));
  const serviceMap = new Map(services.map((item) => [item.id, item.name]));
  const staffMap = new Map(staff.map((item) => [item.id, `${item.first_name} ${item.last_name}`.trim()]));
  const doctorMap = new Map(doctors.map((item) => [item.id, staffMap.get(item.staff_id) || "دكتور"]));
  const selectedPatient = patientId ? patients[0] : null;
  const canOverrideCancellation = ctx.workspace.role === "admin";
  // This async Server Component takes one request-time snapshot for UI hints only.
  // Every write is revalidated by the backend appointment state machine.
  // eslint-disable-next-line react-hooks/purity
  const now = Date.now();

  return (
    <>
      <PageHeader
        title="المواعيد"
        description={
          selectedPatient
            ? `كل مواعيد ${patientMap.get(selectedPatient.id) || "العميل"} في مكان واحد.`
            : "تابع المواعيد واعرف الحجوزات القادمة من Tia، وغيّر حالة الموعد يدويًا عند الحاجة."
        }
        action={
          selectedPatient ? (
            <Link href={`/patients/${selectedPatient.id}`} className="inline-flex items-center gap-1 text-sm font-bold text-teal-700 hover:text-teal-800">
              الرجوع إلى ملف العميل <ChevronLeft size={15} />
            </Link>
          ) : undefined
        }
      />

      <div className="surface-toolbar mb-4">
        <div className="flex flex-wrap gap-1">
          {scopes.map(([value, label]) => (
            <FilterChip key={value} href={hrefFor(filters, "scope", value)} active={scope === value}>
              {label}
            </FilterChip>
          ))}
        </div>
        <span className="hidden h-7 w-px bg-slate-200 sm:block" />
        <div className="flex flex-wrap gap-1">
          {statuses.map(([value, label]) => (
            <FilterChip key={value || "all"} href={hrefFor(filters, "status", value)} active={status === value}>
              {label}
            </FilterChip>
          ))}
        </div>
        <span className="mr-auto hidden text-xs font-semibold text-[var(--muted)] sm:block">{appointments.length} موعد</span>
      </div>

      <Card>
        <CardContent className="p-0 sm:p-0">
          {appointments.length ? (
            <>
              <div className="divide-y divide-[var(--border)] md:hidden">
                {appointments.map((appointment) => (
                  <div key={appointment.id} className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <Link href={`/patients/${appointment.patient_id}`} className="truncate text-sm font-black text-teal-800 hover:underline">
                          {patientMap.get(appointment.patient_id) || "عميل"}
                        </Link>
                        <div className="mt-1 text-sm font-semibold text-slate-700">{serviceMap.get(appointment.service_id) || "خدمة"}</div>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-700">{bookingMethod(appointment.source)}</span>
                    </div>

                    <div className="mt-3 rounded-xl bg-slate-50 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-bold text-slate-900">{formatDateTime(appointment.start_at)}</span>
                        <span className="text-sm font-black text-slate-900">{formatMoney(appointment.price_minor, appointment.currency)}</span>
                      </div>
                      <div className="mt-2 text-xs text-[var(--muted)]">
                        <span className="inline-flex items-center gap-1"><Stethoscope size={13} />{doctorMap.get(appointment.doctor_id) || "دكتور"}</span>
                      </div>
                    </div>

                    <div className="mt-3">
                      <StatusControl appointment={appointment} patientId={appointment.patient_id} canOverrideCancellation={canOverrideCancellation} now={now} />
                    </div>
                  </div>
                ))}
              </div>

              <div className="table-shell hidden md:block">
                <table className="data-table min-w-[900px]">
                  <thead>
                    <tr>
                      <th>العميل</th>
                      <th>الموعد</th>
                      <th>الخدمة</th>
                      <th>الدكتور</th>
                      <th>السعر</th>
                      <th>طريقة الحجز</th>
                      <th>الحالة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {appointments.map((appointment) => (
                      <tr key={appointment.id}>
                        <td className="font-bold">
                          <Link href={`/patients/${appointment.patient_id}`} className="text-teal-800 hover:underline">
                            {patientMap.get(appointment.patient_id) || "عميل"}
                          </Link>
                        </td>
                        <td className="whitespace-nowrap font-semibold text-slate-800">{formatDateTime(appointment.start_at)}</td>
                        <td>{serviceMap.get(appointment.service_id) || "خدمة"}</td>
                        <td>{doctorMap.get(appointment.doctor_id) || "دكتور"}</td>
                        <td className="whitespace-nowrap font-semibold">{formatMoney(appointment.price_minor, appointment.currency)}</td>
                        <td><span className="font-semibold text-slate-700">{bookingMethod(appointment.source)}</span></td>
                        <td><StatusControl appointment={appointment} patientId={appointment.patient_id} canOverrideCancellation={canOverrideCancellation} now={now} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <EmptyState icon={CalendarClock} title="لا توجد مواعيد مطابقة" description="غيّر الفترة أو الحالة لعرض مواعيد أخرى." />
          )}
        </CardContent>
      </Card>
    </>
  );
}
