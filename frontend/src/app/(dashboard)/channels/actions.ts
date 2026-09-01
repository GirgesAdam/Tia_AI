"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { ChannelConnection } from "@/lib/types";

export async function updateAiFollowupTemplate(formData: FormData) {
  const connectionId = String(formData.get("connection_id") || "").trim();
  const name = String(formData.get("template_name") || "").trim();
  const languageCode = String(formData.get("template_language") || "ar").trim() || "ar";
  if (!connectionId) return;

  const connection = await tiaRequest<ChannelConnection>(`/channels/connections/${connectionId}`);
  const config = { ...(connection.config_json || {}) } as Record<string, unknown>;
  if (name) {
    config.ai_followup_template = { name, language_code: languageCode };
  } else {
    delete config.ai_followup_template;
  }
  await tiaRequest(`/channels/connections/${connectionId}`, {
    method: "PATCH",
    body: JSON.stringify({ config }),
  });
  revalidatePath("/channels");
}
