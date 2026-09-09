"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function revalidatePatient(patientId: string) {
  revalidatePath(`/patients/${patientId}`);
  revalidatePath("/patients");
}

function revalidatePackageViews(patientId: string) {
  revalidatePatient(patientId);
  revalidatePath("/dashboard");
  revalidatePath("/finance");
  revalidatePath("/analytics");
}

function moneyToMinor(raw: string) {
  const normalized = raw.trim().replace(",", ".");
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) {
    throw new Error("اكتب مبلغ صحيح بحد أقصى رقمين عشريين.");
  }
  const [whole, fraction = ""] = normalized.split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

export async function addPatientNote(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "");
  const content = String(formData.get("content") || "").trim();
  const noteType = String(formData.get("note_type") || "general");
  if (!patientId || !content) return;

  await tiaRequest(`/crm/patients/${patientId}/notes`, {
    method: "POST",
    body: JSON.stringify({
      note_type: noteType,
      content,
      is_pinned: true,
    }),
  });
  revalidatePatient(patientId);
}

export async function setPatientWhatsappOptIn(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "").trim();
  const whatsappOptIn = String(formData.get("whatsapp_opt_in") || "false") === "true";
  if (!patientId) return;

  await tiaRequest(`/crm/patients/${patientId}`, {
    method: "PATCH",
    body: JSON.stringify({ whatsapp_opt_in: whatsappOptIn }),
  });
  revalidatePatient(patientId);
}

export async function createPatientTask(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "");
  const title = String(formData.get("title") || "").trim();
  const dueAt = String(formData.get("due_at") || "");
  const assignedUserId = String(formData.get("assigned_user_id") || "");
  const executionMode = String(formData.get("execution_mode") || "ai") === "human" ? "human" : "ai";
  const conversationId = String(formData.get("conversation_id") || "");
  const description = String(formData.get("description") || "").trim();
  if (!patientId || !title || !dueAt) return;

  await tiaRequest("/crm/tasks", {
    method: "POST",
    body: JSON.stringify({
      patient_id: patientId,
      conversation_id: conversationId || null,
      assigned_user_id: executionMode === "human" ? (assignedUserId || null) : null,
      task_type: "follow_up",
      execution_mode: executionMode,
      priority: "normal",
      title,
      description: description || null,
      due_at: dueAt,
    }),
  });
  revalidatePatient(patientId);
  revalidatePath("/tasks");
}

export async function purchasePatientPackage(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "").trim();
  const offerId = String(formData.get("offer_id") || "").trim();
  const initialPayment = String(formData.get("initial_payment") || "0").trim() || "0";
  const requestedPaymentMethod = String(formData.get("payment_method") || "").trim();
  if (!patientId || !offerId) return;

  const amountPaidMinor = moneyToMinor(initialPayment);
  const paymentMethod = amountPaidMinor > 0 ? requestedPaymentMethod : "unknown";
  if (amountPaidMinor > 0 && !paymentMethod) return;

  await tiaRequest("/booking/package-offers/purchase", {
    method: "POST",
    headers: { "Idempotency-Key": `dashboard-package-purchase:${randomUUID()}` },
    body: JSON.stringify({
      patient_id: patientId,
      offer_id: offerId,
      amount_paid_minor: amountPaidMinor,
      payment_method: paymentMethod,
    }),
  });
  revalidatePackageViews(patientId);
}

export async function recordPatientPackagePayment(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "").trim();
  const packageId = String(formData.get("package_id") || "").trim();
  const amount = String(formData.get("amount") || "").trim();
  const paymentMethod = String(formData.get("payment_method") || "").trim();
  if (!patientId || !packageId || !amount || !paymentMethod) return;

  await tiaRequest(`/booking/patient-packages/${packageId}/payments`, {
    method: "POST",
    headers: { "Idempotency-Key": `dashboard-package-payment:${randomUUID()}` },
    body: JSON.stringify({
      amount_minor: moneyToMinor(amount),
      payment_method: paymentMethod,
      external_reference: null,
    }),
  });
  revalidatePackageViews(patientId);
}
