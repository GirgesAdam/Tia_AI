"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { TiaApiError, tiaRequest } from "@/lib/tia/api";
import type { Appointment } from "@/lib/types";

function refreshAppointmentViews(appointmentId: string, patientId?: string) {
  revalidatePath("/appointments");
  revalidatePath("/doctors");
  revalidatePath(`/appointments/${appointmentId}`);
  if (patientId) revalidatePath(`/patients/${patientId}`);
  revalidatePath("/dashboard");
  revalidatePath("/finance");
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

export type AppointmentServiceChangeState = { ok: boolean; error: string | null };

function serviceChangeError(error: unknown) {
  if (!(error instanceof TiaApiError)) return "تعذر تعديل الخدمة. حاول مرة أخرى.";
  const detail = error.technicalMessage || "";
  if (detail.includes("not available for the selected service/device with the selected doctor")) {
    return "الخدمة أو الجهاز الجديد مش متاحين في نفس الميعاد مع الدكتور المختار. اختار دكتور تاني أو غيّر الموعد.";
  }
  if (detail.includes("not assigned") || detail.includes("does not provide")) {
    return "الدكتور المختار غير متاح لتنفيذ الخدمة دي. اختار دكتور تاني للخدمة.";
  }
  if (detail.includes("device") && detail.includes("price")) {
    return "سعر جهاز الليزر المختار غير مفعّل للخدمة دي.";
  }
  return error.message;
}

export async function changeAppointmentService(
  _previous: AppointmentServiceChangeState,
  formData: FormData,
): Promise<AppointmentServiceChangeState> {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const serviceId = String(formData.get("service_id") || "");
  const doctorId = String(formData.get("doctor_id") || "").trim();
  const laserDeviceKey = String(formData.get("laser_device_key") || "").trim();
  if (!appointmentId || !serviceId || !doctorId) {
    return { ok: false, error: "اختار الخدمة والدكتور قبل الحفظ." };
  }
  try {
    await tiaRequest(`/booking/appointments/${appointmentId}/service`, {
      method: "POST",
      body: JSON.stringify({
        service_id: serviceId,
        doctor_id: doctorId,
        laser_device_key: laserDeviceKey || null,
      }),
    });
    refreshAppointmentViews(appointmentId, patientId || undefined);
    return { ok: true, error: null };
  } catch (error) {
    return { ok: false, error: serviceChangeError(error) };
  }
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

export async function addAppointmentProduct(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const productId = String(formData.get("product_id") || "");
  const unitPrice = String(formData.get("unit_price") || "");
  const quantity = Math.max(1, Number(String(formData.get("quantity") || "1")) || 1);
  if (!appointmentId || !productId || !unitPrice) return;
  await tiaRequest(`/inventory/appointments/${appointmentId}/products`, {
    method: "POST",
    body: JSON.stringify({
      product_id: productId,
      quantity,
      unit_price_minor: moneyToMinor(unitPrice),
    }),
  });
  refreshAppointmentViews(appointmentId, patientId || undefined);
}

export async function removeAppointmentProduct(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const lineId = String(formData.get("line_id") || "");
  if (!appointmentId || !lineId) return;
  await tiaRequest(`/inventory/appointments/${appointmentId}/products/${lineId}`, { method: "DELETE" });
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
