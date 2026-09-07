"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Branch, Doctor, PatientPackage, Service, Staff } from "@/lib/types";
import { createManualAppointment, type ManualAppointmentState } from "./actions";

const initialState: ManualAppointmentState = { ok: false, message: "" };

export function ManualAppointmentForm({
  mode,
  patientId,
  patientName,
  branches,
  services,
  doctors,
  staff,
  packages = [],
}: {
  mode: "existing" | "new";
  patientId?: string;
  patientName?: string;
  branches: Branch[];
  services: Service[];
  doctors: Doctor[];
  staff: Staff[];
  packages?: PatientPackage[];
}) {
  const [state, formAction, pending] = useActionState(createManualAppointment, initialState);
  const staffMap = new Map(staff.map((item) => [item.id, `${item.first_name} ${item.last_name}`.trim()]));

  return (
    <form action={formAction} className="space-y-4">
      <input type="hidden" name="customer_mode" value={mode} />
      {mode === "existing" && <input type="hidden" name="patient_id" value={patientId} />}

      {mode === "new" ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <label>
              <span className="mb-1.5 block text-xs font-bold text-slate-600">اسم العميل</span>
              <Input name="first_name" required maxLength={120} placeholder="الاسم" />
            </label>
            <label>
              <span className="mb-1.5 block text-xs font-bold text-slate-600">رقم الهاتف</span>
              <Input name="phone" required maxLength={40} dir="ltr" placeholder="01xxxxxxxxx" />
            </label>
          </div>
          <label className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs font-semibold text-slate-700">
            <input name="whatsapp_opt_in" type="checkbox" className="mt-0.5" />
            <span>العميل وافق بوضوح أن العيادة تبدأ معه رسائل واتساب مثل تذكير الموعد والمتابعة.</span>
          </label>
        </>
      ) : (
        <div className="rounded-xl bg-slate-50 px-3 py-2 text-sm font-bold text-slate-800">
          العميل: {patientName || "عميل"}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">الخدمة</span>
          <Select name="service_id" required defaultValue="">
            <option value="" disabled>اختار الخدمة</option>
            {services.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </Select>
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">الدكتور</span>
          <Select name="doctor_id" required defaultValue="">
            <option value="" disabled>اختار الدكتور</option>
            {doctors.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{staffMap.get(item.staff_id) || "دكتور"}</option>)}
          </Select>
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">الفرع</span>
          <Select name="branch_id" required defaultValue={branches.length === 1 ? branches[0].id : ""}>
            {branches.length !== 1 && <option value="" disabled>اختار الفرع</option>}
            {branches.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </Select>
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">التاريخ والوقت</span>
          <Input name="start_at" type="datetime-local" required />
        </label>
      </div>

      {mode === "existing" && packages.length > 0 && (
        <label className="block max-w-md">
          <span className="mb-1.5 block text-xs font-bold text-slate-600">الباكدج (اختياري)</span>
          <Select name="patient_package_id" defaultValue="">
            <option value="">بدون باكدج</option>
            {packages.map((item) => (
              <option key={item.id} value={item.id}>{item.name} · متبقي {item.sessions_remaining}</option>
            ))}
          </Select>
          <span className="mt-1 block text-[11px] text-[var(--muted)]">الـbackend سيتأكد أن الباكدج مناسبة للخدمة والموعد قبل الحجز.</span>
        </label>
      )}

      {state.message && (
        <div className={`rounded-xl px-3 py-2 text-sm font-bold ${state.ok ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>
          {state.message}
        </div>
      )}

      <div className="flex justify-end">
        <Button type="submit" disabled={pending}>{pending ? "جارٍ التسجيل..." : "تسجيل الموعد"}</Button>
      </div>
    </form>
  );
}
