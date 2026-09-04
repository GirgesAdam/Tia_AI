"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

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

export async function saveAutomationTemplates(formData: FormData) {
  const id = String(formData.get("rule_id") || "").trim();
  const primaryName = String(formData.get("template_name") || "").trim();
  const language = String(formData.get("template_language") || "ar").trim() || "ar";
  const rawVariants = String(formData.get("template_variants") || "");

  const seen = new Set<string>();
  const names = rawVariants
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean)
    .filter((name) => {
      if (name === primaryName || seen.has(name)) return false;
      seen.add(name);
      return true;
    })
    .slice(0, 20);

  await tiaRequest(`/automations/rules/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      template_name: primaryName,
      template_language: language,
      template_variants: names.map((name) => ({ name, language_code: language })),
    }),
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
