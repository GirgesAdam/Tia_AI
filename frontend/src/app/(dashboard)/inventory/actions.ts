"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function numberValue(value: FormDataEntryValue | null) {
  const result = Number(String(value || "0"));
  if (!Number.isFinite(result) || result < 0) throw new Error("اكتب كمية صحيحة.");
  return result;
}

function integerValue(value: FormDataEntryValue | null) {
  const result = numberValue(value);
  if (!Number.isInteger(result)) throw new Error("اكتب عدد صحيح.");
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
      quantity_on_hand: integerValue(formData.get("quantity_on_hand")),
    }),
  });
  revalidatePath("/inventory");
  revalidatePath("/appointments");
}

export async function updateClinicProductQuantity(formData: FormData) {
  const id = String(formData.get("product_id") || "");
  if (!id) return;
  await tiaRequest(`/inventory/products/${id}/quantity`, {
    method: "PUT",
    body: JSON.stringify({ quantity_on_hand: integerValue(formData.get("quantity_on_hand")) }),
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
      used_ml: numberValue(formData.get("used_ml")),
      note: String(formData.get("note") || "").trim() || null,
    }),
  });
  revalidatePath("/inventory");
}
