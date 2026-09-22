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

export async function updateLaserPulses(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const pulsesUsed = Number(String(formData.get("pulses_used") || ""));
  if (!appointmentId || !Number.isInteger(pulsesUsed) || pulsesUsed < 0) return;
  await tiaRequest(`/booking/appointments/${appointmentId}/laser-usage`, {
    method: "PUT",
    body: JSON.stringify({ pulses_used: pulsesUsed }),
  });
  refreshAppointmentViews(appointmentId, patientId || undefined);
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
  if (!(error instanceof TiaApiError)) return "تعذر تعديل الموعد. حاول مرة أخرى.";
  const detail = error.technicalMessage || "";
  if (
    detail.includes("not available for the selected service/device with the selected doctor") ||
    detail.includes("Requested appointment time is not available")
  ) {
    return "الخدمة أو الجهاز أو الدكتور مش متاحين في الوقت المختار. غيّر الوقت أو اختار دكتور تاني.";
  }
  if (detail.includes("another appointment") || detail.includes("already booked at this time")) {
    return "فيه تعارض مع موعد تاني للدكتور أو الجهاز في الوقت ده. اختار وقت مختلف.";
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
  const startAt = String(formData.get("start_at") || "").trim();
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
        start_at: startAt || null,
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
  const amount = String(formData.get("amount") || "0");
  const discount = String(formData.get("discount") || "0");
  const paymentMethod = String(formData.get("payment_method") || "");
  const externalReference = String(formData.get("external_reference") || "").trim();
  if (!appointmentId || !paymentMethod) return;
  const amountMinor = moneyToMinor(amount);
  const discountMinor = moneyToMinor(discount);
  if (amountMinor === 0) {
    await tiaRequest(`/payments/appointments/${appointmentId}/discount`, {
      method: "PUT",
      body: JSON.stringify({ discount_minor: discountMinor }),
    });
  } else {
    await tiaRequest(`/payments/appointments/${appointmentId}/payments`, {
      method: "POST",
      headers: { "Idempotency-Key": `dashboard-payment:${randomUUID()}` },
      body: JSON.stringify({
        amount_minor: amountMinor,
        discount_minor: discountMinor,
        payment_method: paymentMethod,
        external_reference: externalReference || null,
      }),
    });
  }
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

function appointmentCommerceError(error: unknown) {
  if (!(error instanceof TiaApiError)) return "تعذر حفظ تعديل الزيارة. حاول مرة أخرى.";
  const detail = error.technicalMessage || "";
  if (detail.includes("primary appointment service")) return "الخدمة الأساسية موجودة بالفعل في الموعد.";
  if (detail.includes("already attached")) return "الخدمة الإضافية موجودة بالفعل في الزيارة.";
  if (detail.includes("laser device")) return "اختار جهاز الليزر الصحيح للخدمة.";
  if (detail.includes("existing appointment payment")) return "فيه دفعة مسجلة على الموعد. راجعها أو استردها أولًا قبل تحويل الجلسة لباكيدج.";
  if (detail.includes("different service") || detail.includes("different laser device")) return "الباكيدج المختارة لا تطابق الخدمة أو جهاز الليزر في الموعد.";
  if (detail.includes("already linked to a package")) return "الخدمة مرتبطة بباكيدج بالفعل.";
  if (detail.includes("package-backed additional service")) return "الخدمة الإضافية مرتبطة بباكيدج، لذلك لا يمكن حذفها كخدمة عادية.";
  return error.message;
}

export async function addAppointmentAdditionalService(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const serviceId = String(formData.get("service_id") || "");
  const laserDeviceKey = String(formData.get("laser_device_key") || "").trim();
  if (!appointmentId || !serviceId) return;
  let errorMessage: string | null = null;
  try {
    await tiaRequest(`/booking/appointments/${appointmentId}/additional-services`, {
      method: "POST",
      body: JSON.stringify({ service_id: serviceId, laser_device_key: laserDeviceKey || null }),
    });
  } catch (error) {
    errorMessage = appointmentCommerceError(error);
  }
  if (errorMessage) redirect(`/appointments/${appointmentId}?visit_error=${encodeURIComponent(errorMessage)}`);
  refreshAppointmentViews(appointmentId, patientId || undefined);
  redirect(`/appointments/${appointmentId}?visit_saved=service`);
}

export async function removeAppointmentAdditionalService(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const lineId = String(formData.get("line_id") || "");
  if (!appointmentId || !lineId) return;
  let errorMessage: string | null = null;
  try {
    await tiaRequest(`/booking/appointments/${appointmentId}/additional-services/${lineId}`, { method: "DELETE" });
  } catch (error) {
    errorMessage = appointmentCommerceError(error);
  }
  if (errorMessage) redirect(`/appointments/${appointmentId}?visit_error=${encodeURIComponent(errorMessage)}`);
  refreshAppointmentViews(appointmentId, patientId || undefined);
  redirect(`/appointments/${appointmentId}?visit_saved=service_removed`);
}

export async function purchasePackageFromAppointment(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const offerId = String(formData.get("offer_id") || "");
  if (!appointmentId || !offerId) return;
  let errorMessage: string | null = null;
  try {
    await tiaRequest(`/booking/appointments/${appointmentId}/package-offer`, {
      method: "POST",
      headers: { "Idempotency-Key": `appointment-package:${randomUUID()}` },
      body: JSON.stringify({ offer_id: offerId }),
    });
  } catch (error) {
    errorMessage = appointmentCommerceError(error);
  }
  if (errorMessage) redirect(`/appointments/${appointmentId}?visit_error=${encodeURIComponent(errorMessage)}`);
  refreshAppointmentViews(appointmentId, patientId || undefined);
  redirect(`/appointments/${appointmentId}?visit_saved=package`);
}

export async function purchasePackageForAdditionalService(formData: FormData) {
  const appointmentId = String(formData.get("appointment_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const lineId = String(formData.get("line_id") || "");
  const offerId = String(formData.get("offer_id") || "");
  if (!appointmentId || !lineId || !offerId) return;
  let errorMessage: string | null = null;
  try {
    await tiaRequest(
      `/booking/appointments/${appointmentId}/additional-services/${lineId}/package-offer`,
      {
        method: "POST",
        headers: { "Idempotency-Key": `appointment-extra-package:${lineId}:${randomUUID()}` },
        body: JSON.stringify({ offer_id: offerId }),
      },
    );
  } catch (error) {
    errorMessage = appointmentCommerceError(error);
  }
  if (errorMessage) redirect(`/appointments/${appointmentId}?visit_error=${encodeURIComponent(errorMessage)}`);
  refreshAppointmentViews(appointmentId, patientId || undefined);
  redirect(`/appointments/${appointmentId}?visit_saved=extra_package`);
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
