"use server";

import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function moneyMinor(value: FormDataEntryValue | null) {
  const amount = Number(String(value || "0"));
  if (!Number.isFinite(amount) || amount < 0) throw new Error("اكتب سعر صحيح.");
  return Math.round(amount * 100);
}

export async function updateServicePricing(formData: FormData) {
  const serviceId = String(formData.get("service_id") || "");
  const requiresLaserDevice = formData.get("requires_laser_device") === "1";
  if (!serviceId) return;
  await tiaRequest(`/clinic/services/${serviceId}`, {
    method: "PATCH",
    body: JSON.stringify({
      price_minor: moneyMinor(formData.get("price")),
      requires_laser_device: requiresLaserDevice,
    }),
  });
  revalidatePath("/services");
  revalidatePath("/appointments");
}

export async function updateLaserDevicePrice(formData: FormData) {
  const serviceId = String(formData.get("service_id") || "");
  const deviceKey = String(formData.get("device_key") || "");
  if (!serviceId || !deviceKey) return;
  await tiaRequest("/inventory/laser-prices", {
    method: "PUT",
    body: JSON.stringify({
      service_id: serviceId,
      device_key: deviceKey,
      price_minor: moneyMinor(formData.get("price")),
      currency: "EGP",
    }),
  });
  revalidatePath("/services");
  revalidatePath("/appointments");
}
