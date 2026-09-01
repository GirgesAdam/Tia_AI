"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";
import type { HistoricalBatch, HistoricalPreview } from "@/lib/clinic-setup-v2-types";

export type HistoricalImportActionState = {
  preview: HistoricalPreview | null;
  error: string | null;
};


const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_TOTAL_BYTES = 60 * 1024 * 1024;

function extension(name: string): "csv" | "xlsx" | null {
  const value = name.toLowerCase();
  if (value.endsWith(".csv")) return "csv";
  if (value.endsWith(".xlsx")) return "xlsx";
  return null;
}

export async function previewHistoricalImportAction(
  _previous: HistoricalImportActionState,
  formData: FormData,
): Promise<HistoricalImportActionState> {
  try {
    const files = formData.getAll("files").filter((item): item is File => item instanceof File && item.size > 0);
    if (!files.length) throw new Error("اختار ملف Excel أو CSV واحد على الأقل.");
    if (files.length > 10) throw new Error("الحد الأقصى 10 ملفات في عملية استيراد واحدة.");
    const total = files.reduce((sum, file) => sum + file.size, 0);
    if (total > MAX_TOTAL_BYTES) throw new Error("إجمالي الملفات أكبر من 60MB.");

    const documents = [];
    for (const file of files) {
      const format = extension(file.name);
      if (!format) throw new Error(`الملف ${file.name} غير مدعوم. استخدم .xlsx أو .csv.`);
      if (file.size > MAX_FILE_BYTES) throw new Error(`الملف ${file.name} أكبر من 25MB.`);
      documents.push({
        name: file.name,
        format,
        content_base64: Buffer.from(await file.arrayBuffer()).toString("base64"),
      });
    }

    const mode = String(formData.get("mode") || "append") === "replace_previous_imports"
      ? "replace_previous_imports"
      : "append";
    const preview = await tiaRequest<HistoricalPreview>("/clinic/history/preview", {
      method: "POST",
      body: JSON.stringify({ documents, mode }),
    });
    revalidatePath("/setup/integration");
    return { preview, error: null };
  } catch (error) {
    return { preview: null, error: error instanceof Error ? error.message : "تعذر فحص الملفات." };
  }
}

export async function startHistoricalImportAction(batchId: string): Promise<HistoricalBatch> {
  const result = await tiaRequest<{ batch: HistoricalBatch; import_started: boolean }>(
    `/clinic/history/batches/${batchId}/apply`,
    { method: "POST", body: "{}" },
  );
  revalidatePath("/setup/integration");
  revalidatePath("/patients");
  revalidatePath("/appointments");
  revalidatePath("/analytics");
  return result.batch;
}

export async function readHistoricalImportBatchAction(batchId: string): Promise<HistoricalBatch> {
  const result = await tiaRequest<{ batch: HistoricalBatch; import_started: boolean }>(
    `/clinic/history/batches/${batchId}`,
  );
  return result.batch;
}
