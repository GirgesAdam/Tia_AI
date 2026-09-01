"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { ClinicSetupDraft, ClinicSetupImportResult, ClinicSetupPreviewResult } from "@/lib/clinic-setup-v2-types";

function refresh() {
  revalidatePath("/setup");
  revalidatePath("/knowledge");
  revalidatePath("/dashboard");
}

export type ClinicSetupImportActionState = {
  result: ClinicSetupPreviewResult | null;
  error: string | null;
};

export async function importClinicSetupWorkbookAction(
  _previous: ClinicSetupImportActionState,
  formData: FormData,
): Promise<ClinicSetupImportActionState> {
  try {
    const file = formData.get("file");
    if (!(file instanceof File) || file.size <= 0) throw new Error("اختار ملف Excel.");
    if (!file.name.toLowerCase().endsWith(".xlsx")) throw new Error("استخدم ملف .xlsx فقط.");
    if (file.size > 10 * 1024 * 1024) throw new Error("ملف إعدادات العيادة أكبر من 10MB.");
    const result = await tiaRequest<ClinicSetupPreviewResult>("/clinic/setup-v2/preview", {
      method: "POST",
      body: JSON.stringify({
        name: file.name,
        content_base64: Buffer.from(await file.arrayBuffer()).toString("base64"),
      }),
    });
    return { result, error: null };
  } catch (error) {
    return { result: null, error: error instanceof Error ? error.message : "تعذر قراءة إعدادات العيادة." };
  }
}

export async function applyClinicSetupDraftAction(draft: ClinicSetupDraft): Promise<ClinicSetupImportResult> {
  const result = await tiaRequest<ClinicSetupImportResult>("/clinic/setup-v2/apply-draft", {
    method: "POST",
    body: JSON.stringify({ draft }),
  });
  refresh();
  return result;
}
