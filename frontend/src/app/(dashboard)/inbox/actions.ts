"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
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

export type ReplyActionState = {
  submittedRequestId: string | null;
};

export async function replyToConversation(
  _previousState: ReplyActionState,
  formData: FormData,
): Promise<ReplyActionState> {
  const conversationId = String(formData.get("conversation_id"));
  const content = String(formData.get("content") || "").trim();
  const requestId = String(formData.get("request_id") || "").trim();
  if (!content || !requestId) return { submittedRequestId: null };

  await tiaRequest(`/inbox/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Idempotency-Key": requestId },
    body: JSON.stringify({ content }),
  });
  revalidateConversation(conversationId);
  return { submittedRequestId: requestId };
}

type StaffWhatsappFollowupResult = {
  status: "queued" | "template_pending" | "unavailable";
  conversation_id: string;
};

export async function sendWhatsappFollowup(formData: FormData) {
  const conversationId = String(formData.get("conversation_id") || "").trim();
  if (!conversationId) return;

  const result = await tiaRequest<StaffWhatsappFollowupResult>(
    `/inbox/conversations/${conversationId}/whatsapp-followup`,
    { method: "POST" },
  );
  revalidateConversation(conversationId);

  if (result.status === "template_pending") {
    redirect(`/inbox/${conversationId}?followup=pending`);
  }
  if (result.status === "unavailable") {
    redirect(`/inbox/${conversationId}?followup=unavailable`);
  }
  redirect(`/inbox/${conversationId}`);
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
