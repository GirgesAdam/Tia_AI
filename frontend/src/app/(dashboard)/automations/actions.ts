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
