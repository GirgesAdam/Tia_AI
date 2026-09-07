"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { ChannelConnection } from "@/lib/types";

export async function toggleAutomation(formData: FormData) {
  const id = String(formData.get("rule_id"));
  const enabled = String(formData.get("enabled")) === "true";
  await tiaRequest(`/automations/rules/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  revalidatePath("/automations");
}

export async function saveAutomationTiming(formData: FormData) {
  const id = String(formData.get("rule_id") || "").trim();
  const triggerKind = String(formData.get("trigger_kind") || "").trim();
  const value = Number(formData.get("timing_value"));
  const unit = String(formData.get("timing_unit") || "hours");

  const multipliers: Record<string, number> = {
    minutes: 1,
    hours: 60,
    days: 1440,
  };
  const multiplier = multipliers[unit];
  if (!id || !Number.isInteger(value) || value < 0 || multiplier === undefined) {
    throw new Error("Invalid automation timing.");
  }

  const absoluteMinutes = value * multiplier;
  if (absoluteMinutes > 10080) {
    throw new Error("Automation timing cannot exceed 7 days.");
  }

  let offsetMinutes = absoluteMinutes;
  if (triggerKind === "before_appointment") offsetMinutes = -absoluteMinutes;
  if (triggerKind === "appointment_created") offsetMinutes = 0;

  await tiaRequest(`/automations/rules/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ offset_minutes: offsetMinutes }),
  });
  revalidatePath("/automations");
}

export async function saveAiFollowupTemplates(formData: FormData) {
  const connectionId = String(formData.get("connection_id") || "").trim();
  const languageCode = String(formData.get("template_language") || "ar_EG").trim() || "ar_EG";
  const names = Array.from(
    new Set(
      String(formData.get("template_names") || "")
        .split(/\r?\n/)
        .map((name) => name.trim())
        .filter(Boolean),
    ),
  );
  if (!connectionId) return;

  const connection = await tiaRequest<ChannelConnection>(`/channels/connections/${connectionId}`);
  const config = { ...(connection.config_json || {}) } as Record<string, unknown>;

  if (names.length) {
    config.ai_followup_templates = names.map((name) => ({
      name,
      language_code: languageCode,
    }));
    // Keep the legacy single-template key so older workers/config readers remain compatible.
    config.ai_followup_template = {
      name: names[0],
      language_code: languageCode,
    };
  } else {
    delete config.ai_followup_templates;
    delete config.ai_followup_template;
  }

  await tiaRequest(`/channels/connections/${connectionId}`, {
    method: "PATCH",
    body: JSON.stringify({ config }),
  });
  revalidatePath("/automations");
}

export async function resumeWhatsappConnection(formData: FormData) {
  const id = String(formData.get("connection_id") || "").trim();
  if (!id) return;
  await tiaRequest(`/channels/connections/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "active" }),
  });
  revalidatePath("/automations");
}

export async function retryAutomationJob(formData: FormData) {
  const id = String(formData.get("job_id") || "").trim();
  await tiaRequest(`/automations/jobs/${id}/retry`, { method: "POST" });
  revalidatePath("/automations");
}

export async function cancelAutomationJob(formData: FormData) {
  const id = String(formData.get("job_id") || "").trim();
  await tiaRequest(`/automations/jobs/${id}/cancel`, { method: "POST" });
  revalidatePath("/automations");
}
