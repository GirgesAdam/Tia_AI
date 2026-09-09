"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function numberValue(value: FormDataEntryValue | null) {
  const result = Number(String(value || "0"));
  if (!Number.isFinite(result) || result < 0) throw new Error("اكتب كمية صحيحة.");
  return result;
}

export async function createClinicProduct(formData: FormData) {
  const name = String(formData.get("name") || "").trim();
  if (!name) return;
  await tiaRequest("/inventory/products", {
    method: "POST",
    body: JSON.stringify({
      name,
      description: String(formData.get("description") || "").trim() || null,
    }),
  });
  revalidatePath("/inventory");
  revalidatePath("/appointments");
}

export async function createInventoryItem(formData: FormData) {
  await tiaRequest("/inventory/items", {
    method: "POST",
    body: JSON.stringify({
      name: String(formData.get("name") || "").trim(),
      quantity_ml: numberValue(formData.get("quantity_ml")),
      concentration_mg_per_ml: numberValue(formData.get("concentration_mg_per_ml")),
      low_stock_threshold_ml: formData.get("low_stock_threshold_ml") ? numberValue(formData.get("low_stock_threshold_ml")) : null,
      notes: String(formData.get("notes") || "").trim() || null,
    }),
  });
  revalidatePath("/inventory");
}

export async function addInventoryStock(formData: FormData) {
  const id = String(formData.get("item_id") || "");
  if (!id) return;
  await tiaRequest(`/inventory/items/${id}/stock`, {
    method: "POST",
    body: JSON.stringify({ quantity_ml: numberValue(formData.get("quantity_ml")) }),
  });
  revalidatePath("/inventory");
}

export async function recordInventoryUsage(formData: FormData) {
  const id = String(formData.get("item_id") || "");
  if (!id) return;
  await tiaRequest(`/inventory/items/${id}/usage`, {
    method: "POST",
    body: JSON.stringify({
      used_mg: numberValue(formData.get("used_mg")),
      appointment_id: String(formData.get("appointment_id") || "").trim() || null,
      note: String(formData.get("note") || "").trim() || null,
    }),
  });
  revalidatePath("/inventory");
}
