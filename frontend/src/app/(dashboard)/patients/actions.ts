"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function revalidatePatient(patientId: string) {
  revalidatePath(`/patients/${patientId}`);
  revalidatePath("/patients");
}

export async function addPatientNote(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "");
  const content = String(formData.get("content") || "").trim();
  const noteType = String(formData.get("note_type") || "general");
  const isPinned = formData.get("is_pinned") === "on";
  if (!patientId || !content) return;

  await tiaRequest(`/crm/patients/${patientId}/notes`, {
    method: "POST",
    body: JSON.stringify({
      note_type: noteType,
      content,
      is_pinned: isPinned,
    }),
  });
  revalidatePatient(patientId);
}

export async function createPatientTask(formData: FormData) {
  const patientId = String(formData.get("patient_id") || "");
  const title = String(formData.get("title") || "").trim();
  const dueAt = String(formData.get("due_at") || "");
  const priority = String(formData.get("priority") || "normal");
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
      priority,
      title,
      description: description || null,
      due_at: dueAt,
    }),
  });
  revalidatePatient(patientId);
  revalidatePath("/tasks");
}
