"use client";

import { useActionState, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Doctor, PatientPackage, Service, Staff } from "@/lib/types";
import { createManualAppointment, type ManualAppointmentState } from "./actions";

const initialState: ManualAppointmentState = { ok: false, message: "" };
type PricedService = Service & { requires_laser_device?: boolean };
type DevicePackage = PatientPackage & {
  laser_device_key?: string | null;
  laser_device_name?: string | null;
};

export function ManualAppointmentForm({
  mode, phone, defaultStart, patientId, patientName, services, doctors, staff,
  doctorBranchMap, defaultBranchId, packages = [],
}: {
  mode: "existing" | "new";
  phone: string;
  defaultStart: string;
  patientId?: string;
  patientName?: string;
  services: PricedService[];
  doctors: Doctor[];
  staff: Staff[];
  doctorBranchMap: Record<string, string>;
  defaultBranchId?: string;
  packages?: DevicePackage[];
}) {
  const [state, formAction, pending] = useActionState(createManualAppointment, initialState);
  const [doctorId, setDoctorId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [laserDeviceKey, setLaserDeviceKey] = useState("");
  const [packageId, setPackageId] = useState("");
  const staffMap = useMemo(() => new Map(staff.map((item) => [item.id, `${item.first_name} ${item.last_name}`.trim()])), [staff]);
  const branchId = doctorBranchMap[doctorId] || defaultBranchId || "";
  const selectedService = services.find((item) => item.id === serviceId);
  const requiresLaserDevice = Boolean(selectedService?.requires_laser_device);
  const compatiblePackages = useMemo(
    () => packages.filter((item) => {
      if (item.service_id !== serviceId) return false;
      if (!item.laser_device_key) return true;
      return requiresLaserDevice && Boolean(laserDeviceKey) && item.laser_device_key === laserDeviceKey;
    }),
    [packages, serviceId, requiresLaserDevice, laserDeviceKey],
  );

  return (
    <form action={formAction} className="space-y-4">
      <input type="hidden" name="customer_mode" value={mode} />
      <input type="hidden" name="branch_id" value={branchId} />
      {mode === "existing" && <input type="hidden" name="patient_id" value={patientId} />}

      {mode === "new" ? (
        <>
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-bold text-amber-900">الرقم غير مسجل. كمّل بيانات العميل لإنشاء ملفه مع الموعد.</div>
          <div className="grid gap-3 sm:grid-cols-3">
            <label><span className="mb-1.5 block text-xs font-bold text-slate-600">الاسم الأول</span><Input name="first_name" required maxLength={120} placeholder="الاسم" /></label>
            <label><span className="mb-1.5 block text-xs font-bold text-slate-600">اسم العائلة (اختياري)</span><Input name="last_name" maxLength={120} placeholder="اسم العائلة" /></label>
            <label><span className="mb-1.5 block text-xs font-bold text-slate-600">رقم الهاتف</span><Input name="phone" required readOnly value={phone} dir="ltr" /></label>
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-950"><div className="font-black">العميل موجود: {patientName || "عميل"}</div><div className="mt-1 font-semibold" dir="ltr">{phone}</div></div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">الخدمة</span>
          <Select
            name="service_id"
            required
            value={serviceId}
            onChange={(event) => {
              setServiceId(event.target.value);
              setLaserDeviceKey("");
              setPackageId("");
            }}
          >
            <option value="" disabled>اختار الخدمة</option>
            {services.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </Select>
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">الدكتور</span>
          <Select name="doctor_id" required value={doctorId} onChange={(event) => setDoctorId(event.target.value)}>
            <option value="" disabled>اختار الدكتور</option>
            {doctors.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{staffMap.get(item.staff_id) || "دكتور"}</option>)}
          </Select>
        </label>
        <label><span className="mb-1.5 block text-xs font-bold text-slate-600">التاريخ والوقت</span><Input name="start_at" type="datetime-local" required defaultValue={defaultStart} /></label>
      </div>

      {requiresLaserDevice && (
        <label className="block max-w-md">
          <span className="mb-1.5 block text-xs font-bold text-slate-600">جهاز الليزر</span>
          <Select
            name="laser_device_key"
            required
            value={laserDeviceKey}
            onChange={(event) => {
              setLaserDeviceKey(event.target.value);
              setPackageId("");
            }}
          >
            <option value="" disabled>اختار الجهاز</option>
            <option value="prime_lase">Prime Lase</option>
            <option value="candela_gentle">Candela Gentle</option>
          </Select>
          <span className="mt-1 block text-[11px] text-[var(--muted)]">سيتم التحقق من توافر الدكتور والجهاز معًا قبل تسجيل الموعد.</span>
        </label>
      )}

      {doctorId && !branchId && <div className="rounded-xl bg-rose-50 px-3 py-2 text-xs font-bold text-rose-800">الدكتور مرتبط بأكثر من فرع من غير فرع أساسي. حدّد فرعه الأساسي من إعدادات العيادة قبل تسجيل الموعد.</div>}

      {mode === "existing" && serviceId && compatiblePackages.length > 0 && (
        <label className="block max-w-md">
          <span className="mb-1.5 block text-xs font-bold text-slate-600">الباكدج (اختياري)</span>
          <Select name="patient_package_id" value={packageId} onChange={(event) => setPackageId(event.target.value)}>
            <option value="">بدون باكدج</option>
            {compatiblePackages.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · متبقي {item.sessions_remaining}
                {item.laser_device_name ? ` · ${item.laser_device_name}` : ""}
              </option>
            ))}
          </Select>
        </label>
      )}

      {state.message && <div className={`rounded-xl px-3 py-2 text-sm font-bold ${state.ok ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>{state.message}</div>}
      <div className="flex justify-end"><Button type="submit" disabled={pending || !branchId}>{pending ? "جارٍ التسجيل..." : "تسجيل الموعد"}</Button></div>
    </form>
  );
}
