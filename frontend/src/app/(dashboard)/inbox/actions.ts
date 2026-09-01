"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function revalidateConversation(conversationId: string) {
  revalidatePath(`/inbox/${conversationId}`);
  revalidatePath("/inbox");
}

export async function claimHandoff(formData: FormData) {
  const id = String(formData.get("handoff_id"));
  const conversationId = String(formData.get("conversation_id"));
  await tiaRequest(`/inbox/handoffs/${id}/claim`, { method: "POST" });
  revalidateConversation(conversationId);
}

export async function assignHandoff(formData: FormData) {
  const id = String(formData.get("handoff_id"));
  const conversationId = String(formData.get("conversation_id"));
  const userId = String(formData.get("user_id"));
  await tiaRequest(`/inbox/handoffs/${id}/assign`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
  revalidateConversation(conversationId);
}

export async function takeOverConversation(formData: FormData) {
  const conversationId = String(formData.get("conversation_id"));
  await tiaRequest(`/inbox/conversations/${conversationId}/takeover`, {
    method: "POST",
    body: JSON.stringify({
      reason: "Manual takeover from Team Inbox.",
      category: "customer_request",
      priority: "normal",
    }),
  });
  revalidateConversation(conversationId);
}

export async function replyToConversation(formData: FormData) {
  const conversationId = String(formData.get("conversation_id"));
  const content = String(formData.get("content") || "").trim();
  if (!content) return;
  await tiaRequest(`/inbox/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
  revalidateConversation(conversationId);
}

export async function resolveHandoff(formData: FormData) {
  const id = String(formData.get("handoff_id"));
  const conversationId = String(formData.get("conversation_id"));
  const note = String(formData.get("resolution_note") || "").trim();
  const closeConversation = formData.get("close_conversation") === "on";
  await tiaRequest(`/inbox/handoffs/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      resolution_note: note || null,
      conversation_status_after: closeConversation ? "closed" : "open",
    }),
  });
  revalidateConversation(conversationId);
}

export async function markConversationRead(conversationId: string) {
  await tiaRequest(`/inbox/conversations/${conversationId}/read`, { method: "POST" });
  revalidateConversation(conversationId);
}
