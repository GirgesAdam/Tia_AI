"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { ClinicKnowledgeEntryInput } from "@/lib/clinic-knowledge-base-types";
import type { ClinicHour, ClinicSetupV2Snapshot } from "@/lib/clinic-setup-v2-types";

function refresh() {
  revalidatePath("/setup");
  revalidatePath("/dashboard");
}

export async function saveClinicProfileAction(payload: {
  name: string;
  phone: string | null;
  address: string | null;
  city: string | null;
}) {
  await tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2/profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  refresh();
}

export async function saveClinicHoursAction(intervals: ClinicHour[]) {
  await tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2/hours", {
    method: "PUT",
    body: JSON.stringify({ intervals }),
  });
  refresh();
}

export async function saveBookingPolicyAction(payload: ClinicSetupV2Snapshot["booking_policy"]) {
  await tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2/booking-policy", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  refresh();
}

export async function createKnowledgeEntryAction(payload: ClinicKnowledgeEntryInput) {
  await tiaRequest("/clinic/knowledge-base", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  refresh();
}

export async function updateKnowledgeEntryAction(id: string, payload: ClinicKnowledgeEntryInput) {
  await tiaRequest(`/clinic/knowledge-base/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  refresh();
}

export async function deleteKnowledgeEntryAction(id: string) {
  await tiaRequest(`/clinic/knowledge-base/${id}`, { method: "DELETE" });
  refresh();
}
