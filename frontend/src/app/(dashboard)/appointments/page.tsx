import Link from "next/link";
import { CalendarClock, ChevronLeft, ExternalLink, MapPin, Stethoscope } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FilterChip } from "@/components/ui/filter-chip";
import { formatDateTime, formatMoney } from "@/lib/format";
import { appointmentLabels, labelForSource, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import type { Appointment, AppointmentStatus, Branch, Doctor, Patient, Service, Staff } from "@/lib/types";

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

  const [appointments, patients, branches, services, doctors, staff] = await Promise.all([
    tiaRequest<Appointment[]>(`/booking/appointments?${query.toString()}`),
    patientId
      ? tiaRequest<Patient>(`/crm/patients/${patientId}`).then((patient) => [patient])
      : tiaRequest<Patient[]>("/crm/patients?limit=100"),
    tiaRequest<Branch[]>("/clinic/branches"),
    tiaRequest<Service[]>("/clinic/services"),
    tiaRequest<Doctor[]>("/clinic/doctors"),
    tiaRequest<Staff[]>("/clinic/staff"),
  ]);

  const patientMap = new Map(patients.map((item) => [item.id, `${item.first_name} ${item.last_name || ""}`.trim()]));
  const branchMap = new Map(branches.map((item) => [item.id, item.name]));
  const serviceMap = new Map(services.map((item) => [item.id, item.name]));
  const staffMap = new Map(staff.map((item) => [item.id, `${item.first_name} ${item.last_name}`]));
  const doctorMap = new Map(doctors.map((item) => [item.id, staffMap.get(item.staff_id) || "دكتور"]));
  const selectedPatient = patientId ? patients[0] : null;

  return (
    <>
      <PageHeader
        title="المواعيد"
        description={
          selectedPatient
            ? `كل مواعيد ${patientMap.get(selectedPatient.id) || "العميل"} في مكان واحد.`
            : "تابع مواعيد اليوم والمواعيد القادمة، وحدّث حالة أي حجز عند الحاجة."
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
                  <Link key={appointment.id} href={`/appointments/${appointment.id}`} className="block p-4 transition hover:bg-slate-50">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-black text-slate-950">{patientMap.get(appointment.patient_id) || "عميل"}</div>
                        <div className="mt-1 text-sm font-semibold text-slate-700">{serviceMap.get(appointment.service_id) || "خدمة"}</div>
                      </div>
                      <Badge tone={toneForStatus(appointment.status)}>{appointmentLabels[appointment.status] || "غير محدد"}</Badge>
                    </div>

                    <div className="mt-3 rounded-xl bg-slate-50 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-bold text-slate-900">{formatDateTime(appointment.start_at)}</span>
                        <span className="text-sm font-black text-slate-900">{formatMoney(appointment.price_minor, appointment.currency)}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--muted)]">
                        <span className="inline-flex items-center gap-1"><MapPin size={13} />{branchMap.get(appointment.branch_id) || "فرع"}</span>
                        <span className="inline-flex items-center gap-1"><Stethoscope size={13} />{doctorMap.get(appointment.doctor_id) || "دكتور"}</span>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center justify-between text-xs text-[var(--muted)]">
                      <span>{labelForSource(appointment.source)}</span>
                      <span className="inline-flex items-center gap-1 font-bold text-teal-700">فتح الموعد <ChevronLeft size={13} /></span>
                    </div>
                  </Link>
                ))}
              </div>

              <div className="table-shell hidden md:block">
                <table className="data-table min-w-[980px]">
                  <thead>
                    <tr>
                      <th>العميل</th>
                      <th>الموعد</th>
                      <th>الخدمة</th>
                      <th>الفرع والدكتور</th>
                      <th>السعر</th>
                      <th>الحالة</th>
                      <th>طريقة الحجز</th>
                      <th className="w-24">إجراء</th>
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
                        <td>
                          <div>{branchMap.get(appointment.branch_id) || "فرع"}</div>
                          <div className="mt-1 text-xs text-[var(--muted)]">{doctorMap.get(appointment.doctor_id) || "دكتور"}</div>
                        </td>
                        <td className="whitespace-nowrap font-semibold">{formatMoney(appointment.price_minor, appointment.currency)}</td>
                        <td><Badge tone={toneForStatus(appointment.status)}>{appointmentLabels[appointment.status] || "غير محدد"}</Badge></td>
                        <td className="text-[var(--muted)]">{labelForSource(appointment.source)}</td>
                        <td>
                          <Link href={`/appointments/${appointment.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                            فتح <ExternalLink size={13} />
                          </Link>
                        </td>
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
