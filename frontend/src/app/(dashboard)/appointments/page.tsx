import Link from "next/link";
import { CalendarClock, ChevronLeft, Plus, Search, Stethoscope } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterChip } from "@/components/ui/filter-chip";
import { Input } from "@/components/ui/input";
import { formatDateTime, formatMoney } from "@/lib/format";
import { appointmentLabels, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { Appointment, AppointmentStatus, Doctor, Patient, PatientPackage, Service, Staff } from "@/lib/types";
import { changeAppointmentStatus } from "./actions";
import { ManualAppointmentForm } from "./manual-appointment-form";

type SearchParams = { patient_id?: string; scope?: string; status?: string; manual_phone?: string };
type BookingKnowledge = {
  branches: Array<{ id: string; is_active: boolean }>;
  doctors: Array<{ id: string; branches: Array<{ id: string; is_primary: boolean }> }>;
};

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

function normalizePhoneIdentity(value: string | null | undefined) {
  if (!value) return "";
  let normalized = value.trim().replace(/[\s().-]/g, "");
  if (normalized.startsWith("0020") && normalized.length === 14) normalized = `+${normalized.slice(2)}`;
  else if (normalized.startsWith("01") && normalized.length === 11) normalized = `+20${normalized.slice(1)}`;
  else if (normalized.startsWith("20") && normalized.length === 12) normalized = `+${normalized}`;
  return normalized;
}

function phoneSearchVariants(value: string) {
  const identity = normalizePhoneIdentity(value);
  const variants = new Set([value.trim(), identity]);
  if (identity.startsWith("+20") && identity.length === 13) {
    variants.add(`0${identity.slice(3)}`);
    variants.add(identity.slice(1));
    variants.add(`00${identity.slice(1)}`);
  }
  return [...variants].filter(Boolean);
}

function cairoNowForInput() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Cairo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

function availableManualStatuses(appointment: Appointment, now: number): AppointmentStatus[] {
  const started = new Date(appointment.start_at).getTime() <= now;
  if (appointment.status === "pending") return started ? ["completed", "no_show"] : ["confirmed", "cancelled"];
  if (appointment.status === "confirmed") return started ? ["completed", "no_show"] : ["cancelled"];
  if ((appointment.status === "checked_in" || appointment.status === "in_progress") && started) return ["completed", "no_show"];
  return [];
}

function StatusControl({ appointment, patientId, canOverrideCancellation, now }: { appointment: Appointment; patientId: string; canOverrideCancellation: boolean; now: number }) {
  const options = availableManualStatuses(appointment, now);
  if (!options.length) return <Badge tone={toneForStatus(appointment.status)}>{appointmentLabels[appointment.status] || "غير محدد"}</Badge>;
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
  const manualPhone = (raw.manual_phone || "").trim();
  const defaultScope = patientId ? "all" : "today";
  const scope = scopes.some(([value]) => value === raw.scope) ? raw.scope! : defaultScope;
  const status = statuses.some(([value]) => value === raw.status) ? raw.status || "" : "";
  const filters: SearchParams = { patient_id: patientId, scope, status };

  const query = new URLSearchParams({ limit: "200", scope });
  if (patientId) query.set("patient_id", patientId);
  if (status) query.set("status", status);

  const [appointments, patients, services, doctors, staff, knowledge, ctx] = await Promise.all([
    tiaRequest<Appointment[]>(`/booking/appointments?${query.toString()}`),
    patientId ? tiaRequest<Patient>(`/crm/patients/${patientId}`).then((patient) => [patient]) : tiaRequest<Patient[]>("/crm/patients?limit=100"),
    tiaRequest<Service[]>("/clinic/services"),
    tiaRequest<Doctor[]>("/clinic/doctors"),
    tiaRequest<Staff[]>("/clinic/staff"),
    tiaRequest<BookingKnowledge>("/clinic/knowledge"),
    getAppContext(),
  ]);

  let manualPatient: Patient | null = null;
  if (manualPhone) {
    const resultSets = await Promise.all(phoneSearchVariants(manualPhone).map((variant) =>
      tiaRequest<Patient[]>(`/crm/patients?q=${encodeURIComponent(variant)}&limit=20`).catch(() => []),
    ));
    const identity = normalizePhoneIdentity(manualPhone);
    const candidates = [...new Map(resultSets.flat().map((patient) => [patient.id, patient])).values()];
    manualPatient = candidates.find((patient) => normalizePhoneIdentity(patient.phone) === identity) || null;
  }

  const [manualPackages, manualHistory] = manualPatient
    ? await Promise.all([
        tiaRequest<PatientPackage[]>(`/booking/patients/${manualPatient.id}/packages?usable_only=true`).catch(() => []),
        tiaRequest<Appointment[]>(`/booking/appointments?patient_id=${manualPatient.id}&scope=all&limit=20`).catch(() => []),
      ])
    : [[], []];

  const activeBranches = knowledge.branches.filter((branch) => branch.is_active);
  const defaultBranchId = activeBranches.length === 1 ? activeBranches[0].id : undefined;
  const doctorBranchMap = Object.fromEntries(knowledge.doctors.map((doctor) => {
    const primary = doctor.branches.find((branch) => branch.is_primary);
    const resolved = primary?.id || (doctor.branches.length === 1 ? doctor.branches[0].id : defaultBranchId || "");
    return [doctor.id, resolved];
  }));

  const patientMap = new Map(patients.map((item) => [item.id, `${item.first_name} ${item.last_name || ""}`.trim()]));
  const serviceMap = new Map(services.map((item) => [item.id, item.name]));
  const staffMap = new Map(staff.map((item) => [item.id, `${item.first_name} ${item.last_name}`.trim()]));
  const doctorMap = new Map(doctors.map((item) => [item.id, staffMap.get(item.staff_id) || "دكتور"]));
  const selectedPatient = patientId ? patients[0] : null;
  const canOverrideCancellation = ctx.workspace.role === "admin";
  const defaultStart = cairoNowForInput();
  // eslint-disable-next-line react-hooks/purity
  const now = Date.now();

  return (
    <>
      <PageHeader
        title="المواعيد"
        description={selectedPatient ? `كل مواعيد ${patientMap.get(selectedPatient.id) || "العميل"} في مكان واحد.` : "تابع المواعيد وسجّل الحجوزات اليدوية من الاستقبال أو التليفون بدون تجاوز قواعد الحجز."}
        action={selectedPatient ? <Link href={`/patients/${selectedPatient.id}`} className="inline-flex items-center gap-1 text-sm font-bold text-teal-700 hover:text-teal-800">الرجوع إلى ملف العميل <ChevronLeft size={15} /></Link> : undefined}
      />

      {!selectedPatient && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Plus size={18} /> إضافة موعد يدوي</CardTitle>
            <p className="text-xs font-semibold text-[var(--muted)]">ابدأ برقم الهاتف. Tia يحدد تلقائيًا إذا كان العميل موجودًا ويعرض حجوزاته السابقة قبل تسجيل الموعد.</p>
          </CardHeader>
          <CardContent className="space-y-5">
            <form method="get" className="flex max-w-xl gap-2">
              <label className="min-w-0 flex-1">
                <span className="mb-1.5 block text-xs font-bold text-slate-600">رقم هاتف العميل</span>
                <Input name="manual_phone" defaultValue={manualPhone} required maxLength={40} dir="ltr" placeholder="01xxxxxxxxx" />
              </label>
              <Button type="submit" variant="outline" className="mt-6"><Search size={16} /> بحث</Button>
            </form>

            {manualPhone && (
              <div className="border-t border-slate-100 pt-5">
                {manualPatient && (
                  <div className="mb-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-slate-950">الحجوزات السابقة لـ {manualPatient.first_name} {manualPatient.last_name || ""}</div>
                        <div className="mt-1 text-xs text-[var(--muted)]">آخر {Math.min(manualHistory.length, 20).toLocaleString("ar-EG")} موعد مسجل لهذا الرقم.</div>
                      </div>
                      <Link href={`/patients/${manualPatient.id}`} className="text-xs font-bold text-teal-700 hover:underline">فتح ملف العميل</Link>
                    </div>
                    {manualHistory.length ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                        {manualHistory.slice(0, 6).map((appointment) => (
                          <div key={appointment.id} className="rounded-xl bg-white px-3 py-2 text-xs">
                            <div className="font-black text-slate-900">{serviceMap.get(appointment.service_id) || "خدمة"}</div>
                            <div className="mt-1 text-slate-600">{formatDateTime(appointment.start_at)}</div>
                            <div className="mt-1 font-bold text-slate-700">{appointmentLabels[appointment.status] || appointment.status}</div>
                          </div>
                        ))}
                      </div>
                    ) : <div className="mt-3 text-xs text-[var(--muted)]">لا توجد حجوزات سابقة لهذا العميل.</div>}
                  </div>
                )}

                <ManualAppointmentForm
                  mode={manualPatient ? "existing" : "new"}
                  phone={manualPhone}
                  defaultStart={defaultStart}
                  patientId={manualPatient?.id}
                  patientName={manualPatient ? `${manualPatient.first_name} ${manualPatient.last_name || ""}`.trim() : undefined}
                  services={services}
                  doctors={doctors}
                  staff={staff}
                  doctorBranchMap={doctorBranchMap}
                  defaultBranchId={defaultBranchId}
                  packages={manualPackages}
                />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="surface-toolbar mb-4">
        <div className="flex flex-wrap gap-1">{scopes.map(([value, label]) => <FilterChip key={value} href={hrefFor(filters, "scope", value)} active={scope === value}>{label}</FilterChip>)}</div>
        <span className="hidden h-7 w-px bg-slate-200 sm:block" />
        <div className="flex flex-wrap gap-1">{statuses.map(([value, label]) => <FilterChip key={value || "all"} href={hrefFor(filters, "status", value)} active={status === value}>{label}</FilterChip>)}</div>
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
                      <div className="min-w-0"><Link href={`/patients/${appointment.patient_id}`} className="truncate text-sm font-black text-teal-800 hover:underline">{patientMap.get(appointment.patient_id) || "عميل"}</Link><div className="mt-1 text-sm font-semibold text-slate-700">{serviceMap.get(appointment.service_id) || "خدمة"}</div></div>
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-700">{bookingMethod(appointment.source)}</span>
                    </div>
                    <div className="mt-3 rounded-xl bg-slate-50 p-3">
                      <div className="flex items-center justify-between gap-3"><span className="text-sm font-bold text-slate-900">{formatDateTime(appointment.start_at)}</span><span className="text-sm font-black text-slate-900">{formatMoney(appointment.price_minor, appointment.currency)}</span></div>
                      <div className="mt-2 text-xs text-[var(--muted)]"><span className="inline-flex items-center gap-1"><Stethoscope size={13} />{doctorMap.get(appointment.doctor_id) || "دكتور"}</span></div>
                    </div>
                    <div className="mt-3"><StatusControl appointment={appointment} patientId={appointment.patient_id} canOverrideCancellation={canOverrideCancellation} now={now} /></div>
                  </div>
                ))}
              </div>

              <div className="table-shell hidden md:block">
                <table className="data-table min-w-[900px]">
                  <thead><tr><th>العميل</th><th>الموعد</th><th>الخدمة</th><th>الدكتور</th><th>السعر</th><th>طريقة الحجز</th><th>الحالة</th></tr></thead>
                  <tbody>{appointments.map((appointment) => (
                    <tr key={appointment.id}>
                      <td className="font-bold"><Link href={`/patients/${appointment.patient_id}`} className="text-teal-800 hover:underline">{patientMap.get(appointment.patient_id) || "عميل"}</Link></td>
                      <td className="whitespace-nowrap font-semibold text-slate-800">{formatDateTime(appointment.start_at)}</td>
                      <td>{serviceMap.get(appointment.service_id) || "خدمة"}</td>
                      <td>{doctorMap.get(appointment.doctor_id) || "دكتور"}</td>
                      <td className="whitespace-nowrap font-semibold">{formatMoney(appointment.price_minor, appointment.currency)}</td>
                      <td><span className="font-semibold text-slate-700">{bookingMethod(appointment.source)}</span></td>
                      <td><StatusControl appointment={appointment} patientId={appointment.patient_id} canOverrideCancellation={canOverrideCancellation} now={now} /></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </>
          ) : <EmptyState icon={CalendarClock} title="لا توجد مواعيد مطابقة" description="غيّر الفترة أو الحالة لعرض مواعيد أخرى." />}
        </CardContent>
      </Card>
    </>
  );
}
