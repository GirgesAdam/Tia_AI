"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function refreshTaskViews(patientId?: string) {
  revalidatePath("/tasks");
  if (patientId) revalidatePath(`/patients/${patientId}`);
}

export async function claimTask(formData: FormData) {
  const taskId = String(formData.get("task_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  if (!taskId) return;
  await tiaRequest(`/crm/tasks/${taskId}/claim`, { method: "POST" });
  refreshTaskViews(patientId || undefined);
}

export async function setTaskStatus(formData: FormData) {
  const taskId = String(formData.get("task_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const status = String(formData.get("status") || "");
  if (!taskId || !status) return;
  await tiaRequest(`/crm/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  refreshTaskViews(patientId || undefined);
}

export async function assignTask(formData: FormData) {
  const taskId = String(formData.get("task_id") || "");
  const patientId = String(formData.get("patient_id") || "");
  const rawUserId = String(formData.get("assigned_user_id") || "");
  if (!taskId) return;
  await tiaRequest(`/crm/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify({ assigned_user_id: rawUserId || null }),
  });
  refreshTaskViews(patientId || undefined);
}
