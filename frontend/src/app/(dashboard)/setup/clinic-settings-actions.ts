"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { ClinicKnowledgeEntryInput, ClinicKnowledgeScope } from "@/lib/clinic-knowledge-base-types";
import type { ClinicHour, ClinicSetupV2Snapshot } from "@/lib/clinic-setup-v2-types";

function refresh() {
  revalidatePath("/setup");
  revalidatePath("/dashboard");
}

function text(formData: FormData, key: string) {
  const value = String(formData.get(key) ?? "").trim();
  return value || null;
}

function integer(formData: FormData, key: string, fallback: number) {
  const parsed = Number.parseInt(String(formData.get(key) ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export async function saveClinicProfileFormAction(formData: FormData) {
  const name = text(formData, "name");
  if (!name) throw new Error("اسم العيادة مطلوب.");
  await tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2/profile", {
    method: "PUT",
    body: JSON.stringify({
      name,
      phone: text(formData, "phone"),
      address: text(formData, "address"),
      city: text(formData, "city"),
    }),
  });
  refresh();
}

export async function saveClinicHoursFormAction(formData: FormData) {
  const intervals: ClinicHour[] = [];
  for (let weekday = 0; weekday < 7; weekday += 1) {
    if (formData.get(`enabled_${weekday}`) !== "on") continue;
    const start = text(formData, `start_${weekday}`);
    const end = text(formData, `end_${weekday}`);
    if (!start || !end) throw new Error("حدد بداية وآخر وقت حجز لكل يوم مفعّل.");
    intervals.push({ weekday, start_time: start, end_time: end });
  }
  await tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2/hours", {
    method: "PUT",
    body: JSON.stringify({ intervals }),
  });
  refresh();
}

export async function saveBookingPolicyFormAction(formData: FormData) {
  const payload: ClinicSetupV2Snapshot["booking_policy"] = {
    slot_interval_minutes: integer(formData, "slot_interval_minutes", 15),
    minimum_notice_minutes: integer(formData, "minimum_notice_minutes", 60),
    booking_horizon_days: integer(formData, "booking_horizon_days", 90),
    cancellation_notice_minutes: integer(formData, "cancellation_notice_minutes", 720),
    allow_same_day_booking: formData.get("allow_same_day_booking") === "on",
    require_confirmation: formData.get("require_confirmation") === "on",
  };
  await tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2/booking-policy", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  refresh();
}

function knowledgePayload(formData: FormData): ClinicKnowledgeEntryInput {
  const scope = String(formData.get("scope_type") ?? "clinic") as ClinicKnowledgeScope;
  const title = text(formData, "title");
  const content = text(formData, "content");
  if (!title || !content) throw new Error("العنوان والمعلومة مطلوبان.");
  return {
    scope_type: scope,
    service_id: scope === "service" ? text(formData, "service_id") : null,
    device_key: scope === "laser_device" ? text(formData, "device_key") : null,
    title,
    content,
    sort_order: integer(formData, "sort_order", 0),
    is_active: formData.get("is_active") === "on",
  };
}

export async function createKnowledgeEntryFormAction(formData: FormData) {
  await tiaRequest("/clinic/knowledge-base", {
    method: "POST",
    body: JSON.stringify(knowledgePayload(formData)),
  });
  refresh();
}

export async function updateKnowledgeEntryFormAction(formData: FormData) {
  const id = text(formData, "id");
  if (!id) throw new Error("Knowledge entry id is missing.");
  await tiaRequest(`/clinic/knowledge-base/${id}`, {
    method: "PUT",
    body: JSON.stringify(knowledgePayload(formData)),
  });
  refresh();
}

export async function deleteKnowledgeEntryFormAction(formData: FormData) {
  const id = text(formData, "id");
  if (!id) throw new Error("Knowledge entry id is missing.");
  await tiaRequest(`/clinic/knowledge-base/${id}`, { method: "DELETE" });
  refresh();
}
