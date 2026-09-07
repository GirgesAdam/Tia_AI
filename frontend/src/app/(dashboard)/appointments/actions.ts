"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { Appointment, Patient } from "@/lib/types";

export type ManualAppointmentState = { ok: boolean; message: string };

function refreshAppointmentViews(appointmentId: string, patientId?: string) {
  revalidatePath("/appointments");
  revalidatePath(`/appointments/${appointmentId}`);
  if (patientId) revalidatePath(`/patients/${patientId}`);
  revalidatePath("/patients");
  revalidatePath("/dashboard");
  revalidatePath("/analytics");
}

function cairoLocalToIso(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("اختار تاريخ ووقت صحيحين.");
  const [, year, month, day, hour, minute] = match;
  const guess = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Cairo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(formatter.formatToParts(new Date(guess)).map((part) => [part.type, part.value]));
  const renderedAsUtc = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  );
  const offsetMs = renderedAsUtc - guess;
  return new Date(guess - offsetMs).toISOString();
}

export async function createManualAppointment(
  previous: ManualAppointmentState,
  formData: FormData,
): Promise<ManualAppointmentState> {
  void previous;
  try {
    const mode = String(formData.get("customer_mode") || "existing");
    let patientId = String(formData.get("patient_id") || "").trim();

    if (mode === "new") {
      const firstName = String(formData.get("first_name") || "").trim();
      const phone = String(formData.get("phone") || "").trim();
      if (!firstName || !phone) return { ok: false, message: "اكتب اسم العميل ورقم الهاتف." };
      const patient = await tiaRequest<Patient>("/crm/patients", {
        method: "POST",
        body: JSON.stringify({
          first_name: firstName,
          phone,
          source: "phone",
          status: "active",
          preferred_language: "ar",
        }),
      });
      patientId = patient.id;
    }

    const branchId = String(formData.get("branch_id") || "").trim();
    const doctorId = String(formData.get("doctor_id") || "").trim();
    const serviceId = String(formData.get("service_id") || "").trim();
    const startsAt = String(formData.get("start_at") || "").trim();
    const packageId = String(formData.get("patient_package_id") || "").trim();
    if (!patientId || !branchId || !doctorId || !serviceId || !startsAt) {
      return { ok: false, message: "كمّل بيانات العميل والخدمة والدكتور والموعد." };
    }

    const appointment = await tiaRequest<Appointment>("/booking/appointments", {
      method: "POST",
      body: JSON.stringify({
        patient_id: patientId,
        branch_id: branchId,
        doctor_id: doctorId,
        service_id: serviceId,
        patient_package_id: packageId || null,
        start_at: cairoLocalToIso(startsAt),
        source: "staff",
      }),
    });

    refreshAppointmentViews(appointment.id, patientId);
    return { ok: true, message: "تم تسجيل الموعد بنجاح." };
  } catch (error) {
    const message = error instanceof Error ? error.message : "تعذر تسجيل الموعد.";
    return { ok: false, message: message.includes("conflict") ? "الوقت غير متاح. اختار موعدًا آخر." : message };
  }
}

export async function changeAppointmentStatus(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const status = String(formData.get("status") || "");
  const canOverrideCancellation = formData.get("can_override_cancellation") === "1";
  if (!appointmentId || !status) return;

  if (status === "confirmed") {
    await tiaRequest(`/booking/appointments/${appointmentId}/confirm`, { method: "POST" });
  } else if (status === "completed" || status === "no_show") {
    await tiaRequest(`/booking/appointments/${appointmentId}/status`, {
      method: "POST",
      body: JSON.stringify({
        status,
        reason: "manual_status_change_from_appointments",
      }),
    });
  } else if (status === "cancelled") {
    await tiaRequest(`/booking/appointments/${appointmentId}/cancel`, {
      method: "POST",
      body: JSON.stringify({
        reason: "تم إلغاء الموعد يدويًا من لوحة المواعيد",
        override_policy: canOverrideCancellation,
      }),
    });
  } else {
    return;
  }

  refreshAppointmentViews(appointmentId, patientId || undefined);
}
