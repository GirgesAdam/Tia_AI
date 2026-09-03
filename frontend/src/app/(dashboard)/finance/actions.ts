"use server";

import { revalidatePath } from "next/cache";

import { tiaRequest } from "@/lib/tia/api";

function parseAmountMinor(value: FormDataEntryValue | null) {
  const raw = String(value || "").trim().replace(",", ".");
  if (!/^\d+(?:\.\d{1,2})?$/.test(raw)) return null;
  const [whole, fraction = ""] = raw.split(".");
  const amount = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(amount) && amount > 0 ? amount : null;
}

function expensePayload(formData: FormData) {
  const title = String(formData.get("title") || "").trim();
  const category = String(formData.get("category") || "other");
  const amountMinor = parseAmountMinor(formData.get("amount"));
  const currency = String(formData.get("currency") || "EGP").trim().toUpperCase();
  const incurredOn = String(formData.get("incurred_on") || "").trim();
  const note = String(formData.get("note") || "").trim();

  if (!title || !amountMinor || !/^\w{3}$/.test(currency) || !/^\d{4}-\d{2}-\d{2}$/.test(incurredOn)) {
    return null;
  }

  return {
    title,
    category,
    amount_minor: amountMinor,
    currency,
    incurred_on: incurredOn,
    note: note || null,
  };
}

export async function createExpense(formData: FormData) {
  const payload = expensePayload(formData);
  if (!payload) return;

  await tiaRequest("/finance/expenses", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  revalidatePath("/finance");
}

export async function updateExpense(formData: FormData) {
  const expenseId = String(formData.get("expense_id") || "").trim();
  const payload = expensePayload(formData);
  if (!expenseId || !payload) return;

  await tiaRequest(`/finance/expenses/${expenseId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  revalidatePath("/finance");
}

export async function deleteExpense(formData: FormData) {
  const expenseId = String(formData.get("expense_id") || "").trim();
  if (!expenseId) return;

  await tiaRequest(`/finance/expenses/${expenseId}`, { method: "DELETE" });
  revalidatePath("/finance");
}
