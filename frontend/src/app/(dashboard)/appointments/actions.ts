"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { Appointment, Patient } from "@/lib/types";

export type ManualAppointmentState = { ok: boolean; message: string };

export type ManualAvailabilitySlot = {
  doctor_id: string;
  start_at: string;
  end_at: string;
  laser_device_key?: string | null;
  laser_device_name?: string | null;
};

export type ManualAvailabilityResult = {
  ok: boolean;
  message: string;
  timezone: string;
  slots: ManualAvailabilitySlot[];
};

type AvailabilityResponse = {
  timezone: string;
  slots: ManualAvailabilitySlot[];
};

function minuteInTimezone(value: string, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return Number(values.hour) * 60 + Number(values.minute);
}

export async function getManualAppointmentAvailability(input: {
  branchId: string;
  serviceId: string;
  date: string;
  laserDeviceKey?: string;
  windowStartMinutes?: number;
  windowEndMinutes?: number;
}): Promise<ManualAvailabilityResult> {
  const branchId = input.branchId.trim();
  const serviceId = input.serviceId.trim();
  const date = input.date.trim();
  if (!branchId || !serviceId || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return { ok: false, message: "بيانات اليوم أو الخدمة غير مكتملة.", timezone: "Africa/Cairo", slots: [] };
  }

  try {
    const query = new URLSearchParams({
      branch_id: branchId,
      service_id: serviceId,
      date,
    });
    if (input.laserDeviceKey) query.set("laser_device_key", input.laserDeviceKey);
    const response = await tiaRequest<AvailabilityResponse>(`/booking/availability?${query.toString()}`);
    const hasWindow =
      Number.isFinite(input.windowStartMinutes) &&
      Number.isFinite(input.windowEndMinutes) &&
      Number(input.windowEndMinutes) > Number(input.windowStartMinutes);
    const slots = hasWindow
      ? response.slots.filter((slot) => {
          const minute = minuteInTimezone(slot.start_at, response.timezone);
          return minute >= Number(input.windowStartMinutes) && minute < Number(input.windowEndMinutes);
        })
      : response.slots;
    return {
      ok: true,
      message: slots.length ? "" : "مفيش مواعيد متاحة للخدمة دي في الفترة المختارة.",
      timezone: response.timezone,
      slots,
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "تعذر تحميل المواعيد المتاحة.",
      timezone: "Africa/Cairo",
      slots: [],
    };
  }
}

function refreshAppointmentViews(appointmentId: string, patientId?: string) {
  revalidatePath("/appointments");
  revalidatePath(`/appointments/${appointmentId}`);
  if (patientId) revalidatePath(`/patients/${patientId}`);
  revalidatePath("/patients");
  revalidatePath("/dashboard");
  revalidatePath("/analytics");
}

function manualStartToIso(value: string) {
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    return cairoLocalToIso(value);
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) throw new Error("اختار وقت صحيح من المواعيد المتاحة.");
  return parsed.toISOString();
}

function cairoLocalToIso(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("اختار تاريخ ووقت صحيحين.");
  const [, year, month, day, hour, minute] = match;
  const guess = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  });
  const parts = Object.fromEntries(formatter.formatToParts(new Date(guess)).map((part) => [part.type, part.value]));
  const renderedAsUtc = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute), Number(parts.second));
  return new Date(guess - (renderedAsUtc - guess)).toISOString();
}

export async function createManualAppointment(previous: ManualAppointmentState, formData: FormData): Promise<ManualAppointmentState> {
  void previous;
  try {
    const mode = String(formData.get("customer_mode") || "existing");
    let patientId = String(formData.get("patient_id") || "").trim();
    if (mode === "new") {
      const firstName = String(formData.get("first_name") || "").trim();
      const lastName = String(formData.get("last_name") || "").trim();
      const phone = String(formData.get("phone") || "").trim();
      if (!firstName || !phone) return { ok: false, message: "اكتب اسم العميل ورقم الهاتف." };
      const patient = await tiaRequest<Patient>("/crm/patients", {
        method: "POST",
        body: JSON.stringify({ first_name: firstName, last_name: lastName || null, phone, source: "phone", status: "active", preferred_language: "ar" }),
      });
      patientId = patient.id;
    }

    const branchId = String(formData.get("branch_id") || "").trim();
    const doctorId = String(formData.get("doctor_id") || "").trim();
    const serviceId = String(formData.get("service_id") || "").trim();
    const startsAt = String(formData.get("start_at") || "").trim();
    const packageId = String(formData.get("patient_package_id") || "").trim();
    const laserDeviceKey = String(formData.get("laser_device_key") || "").trim();
    if (!patientId || !branchId || !doctorId || !serviceId || !startsAt) return { ok: false, message: "كمّل بيانات العميل والخدمة والدكتور والموعد." };

    const appointment = await tiaRequest<Appointment>("/booking/appointments", {
      method: "POST",
      body: JSON.stringify({
        patient_id: patientId,
        branch_id: branchId,
        doctor_id: doctorId,
        service_id: serviceId,
        patient_package_id: packageId || null,
        laser_device_key: laserDeviceKey || null,
        start_at: manualStartToIso(startsAt),
        source: "staff",
      }),
    });
    refreshAppointmentViews(appointment.id, patientId);
    return { ok: true, message: "تم تسجيل الموعد بنجاح." };
  } catch (error) {
    const message = error instanceof Error ? error.message : "تعذر تسجيل الموعد.";
    return { ok: false, message: message.includes("conflict") ? "الوقت أو الجهاز غير متاح. اختار موعدًا آخر." : message };
  }
}

export async function changeAppointmentStatus(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const status = String(formData.get("status") || "");
  const canOverrideCancellation = formData.get("can_override_cancellation") === "1";
  if (!appointmentId || !status) return;
  if (status === "confirmed") await tiaRequest(`/booking/appointments/${appointmentId}/confirm`, { method: "POST" });
  else if (status === "completed" || status === "no_show") await tiaRequest(`/booking/appointments/${appointmentId}/status`, { method: "POST", body: JSON.stringify({ status, reason: "manual_status_change_from_appointments" }) });
  else if (status === "cancelled") await tiaRequest(`/booking/appointments/${appointmentId}/cancel`, { method: "POST", body: JSON.stringify({ reason: "تم إلغاء الموعد يدويًا من لوحة المواعيد", override_policy: canOverrideCancellation }) });
  else return;
  refreshAppointmentViews(appointmentId, patientId || undefined);
}
