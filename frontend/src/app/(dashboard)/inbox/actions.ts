"use server";
import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
export async function claimHandoff(formData:FormData){const id=String(formData.get("handoff_id"));const conversationId=String(formData.get("conversation_id"));await tiaRequest(`/inbox/handoffs/${id}/claim`,{method:"POST"});revalidatePath(`/inbox/${conversationId}`);revalidatePath("/inbox");}
export async function replyToConversation(formData:FormData){const conversationId=String(formData.get("conversation_id"));const content=String(formData.get("content")||"").trim();if(!content)return;await tiaRequest(`/inbox/conversations/${conversationId}/messages`,{method:"POST",body:JSON.stringify({content})});revalidatePath(`/inbox/${conversationId}`);}
export async function resolveHandoff(formData:FormData){const id=String(formData.get("handoff_id"));const conversationId=String(formData.get("conversation_id"));const note=String(formData.get("resolution_note")||"").trim();await tiaRequest(`/inbox/handoffs/${id}/resolve`,{method:"POST",body:JSON.stringify({resolution_note:note||null,conversation_status_after:"open"})});revalidatePath(`/inbox/${conversationId}`);revalidatePath("/inbox");}
