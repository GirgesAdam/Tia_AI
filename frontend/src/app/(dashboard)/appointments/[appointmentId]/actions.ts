"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { tiaRequest } from "@/lib/tia/api";
import type { Appointment } from "@/lib/types";

function refreshAppointmentViews(appointmentId: string, patientId?: string) {
  revalidatePath("/appointments");
  revalidatePath(`/appointments/${appointmentId}`);
  if (patientId) revalidatePath(`/patients/${patientId}`);
  revalidatePath("/analytics");
}

export async function confirmAppointment(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  if (!appointmentId) return;
  await tiaRequest(`/booking/appointments/${appointmentId}/confirm`, { method: "POST" });
  refreshAppointmentViews(appointmentId, patientId || undefined);
}

export async function updateAppointmentStatus(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const status = String(formData.get("status") || "");
  if (!appointmentId || !status) return;
  await tiaRequest(`/booking/appointments/${appointmentId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
  refreshAppointmentViews(appointmentId, patientId || undefined);
}

export async function cancelAppointment(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const reason = String(formData.get("reason") || "").trim();
  const overridePolicy = formData.get("override_policy") === "1" || formData.get("override_policy") === "on";
  if (!appointmentId || !reason) return;
  await tiaRequest(`/booking/appointments/${appointmentId}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason, override_policy: overridePolicy }),
  });
  refreshAppointmentViews(appointmentId, patientId || undefined);
}

function moneyToMinor(raw: string) {
  const normalized = raw.trim().replace(",", ".");
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) throw new Error("اكتب مبلغ صحيح بحد أقصى رقمين عشريين.");
  const [whole, fraction = ""] = normalized.split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

export async function recordAppointmentPayment(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const amount = String(formData.get("amount") || "");
  const paymentMethod = String(formData.get("payment_method") || "");
  const externalReference = String(formData.get("external_reference") || "").trim();
  if (!appointmentId || !amount || !paymentMethod) return;
  await tiaRequest(`/payments/appointments/${appointmentId}/payments`, {
    method: "POST",
    headers: { "Idempotency-Key": `dashboard-payment:${randomUUID()}` },
    body: JSON.stringify({
      amount_minor: moneyToMinor(amount),
      payment_method: paymentMethod,
      external_reference: externalReference || null,
    }),
  });
  refreshAppointmentViews(appointmentId, patientId || undefined);
}

export async function refundAppointmentPayment(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const paymentTransactionId = String(formData.get("payment_transaction_id") || "");
  const amount = String(formData.get("amount") || "");
  const reason = String(formData.get("reason") || "").trim();
  if (!appointmentId || !paymentTransactionId || !amount || !reason) return;
  await tiaRequest(`/payments/appointments/${appointmentId}/refunds`, {
    method: "POST",
    headers: { "Idempotency-Key": `dashboard-refund:${randomUUID()}` },
    body: JSON.stringify({
      payment_transaction_id: paymentTransactionId,
      amount_minor: moneyToMinor(amount),
      reason,
    }),
  });
  refreshAppointmentViews(appointmentId, patientId || undefined);
}

export async function rescheduleAppointment(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const startAt = String(formData.get("start_at") || "");
  if (!appointmentId || !startAt) return;
  const replacement = await tiaRequest<Appointment>(`/booking/appointments/${appointmentId}/reschedule`, {
    method: "POST",
    headers: { "Idempotency-Key": `dashboard:${randomUUID()}` },
    body: JSON.stringify({
      start_at: startAt,
      reason: "appointment_rescheduled_from_operations",
    }),
  });
  revalidatePath("/appointments");
  revalidatePath(`/appointments/${appointmentId}`);
  revalidatePath(`/patients/${replacement.patient_id}`);
  revalidatePath("/analytics");
  redirect(`/appointments/${replacement.id}`);
}
