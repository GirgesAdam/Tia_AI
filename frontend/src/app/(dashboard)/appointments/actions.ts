"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function refreshAppointmentViews(appointmentId: string, patientId?: string) {
  revalidatePath("/appointments");
  revalidatePath(`/appointments/${appointmentId}`);
  if (patientId) revalidatePath(`/patients/${patientId}`);
  revalidatePath("/dashboard");
  revalidatePath("/analytics");
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
