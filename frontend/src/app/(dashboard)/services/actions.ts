"use server";

import { randomUUID } from "crypto";
import { revalidatePath } from "next/cache";
import { tiaRequest } from "@/lib/tia/api";

function moneyMinor(value: FormDataEntryValue | null) {
  const amount = Number(String(value || "0"));
  if (!Number.isFinite(amount) || amount < 0) throw new Error("اكتب سعر صحيح.");
  return Math.round(amount * 100);
}

function positiveInteger(value: FormDataEntryValue | null, fallback: number) {
  const parsed = Number(String(value || fallback));
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error("اكتب مدة صحيحة.");
  return parsed;
}

export async function createService(formData: FormData) {
  const name = String(formData.get("name") || "").trim();
  if (!name) return;
  const requiresLaserDevice = formData.get("requires_laser_device") === "1";
  await tiaRequest("/clinic/services", {
    method: "POST",
    body: JSON.stringify({
      name,
      slug: `service-${randomUUID()}`,
      category: String(formData.get("category") || "").trim() || null,
      description: null,
      duration_minutes: positiveInteger(formData.get("duration_minutes"), 60),
      buffer_before_minutes: 0,
      buffer_after_minutes: 0,
      price_minor: requiresLaserDevice ? 0 : moneyMinor(formData.get("price")),
      currency: "EGP",
      requires_medical_review: false,
      requires_laser_device: requiresLaserDevice,
    }),
  });
  revalidatePath("/services");
  revalidatePath("/appointments");
}

export async function updateServicePricing(formData: FormData) {
  const serviceId = String(formData.get("service_id") || "");
  const name = String(formData.get("name") || "").trim();
  const requiresLaserDevice = formData.get("requires_laser_device") === "1";
  if (!serviceId || !name) return;
  await tiaRequest(`/clinic/services/${serviceId}`, {
    method: "PATCH",
    body: JSON.stringify({
      name,
      price_minor: requiresLaserDevice ? 0 : moneyMinor(formData.get("price")),
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

export async function updatePackageOffer(formData: FormData) {
  const serviceId = String(formData.get("service_id") || "");
  const deviceKey = String(formData.get("device_key") || "");
  const sessionsCount = Number(String(formData.get("sessions_count") || "0"));
  if (!serviceId || !deviceKey || ![3, 6, 9].includes(sessionsCount)) return;
  const active = formData.get("is_active") === "1";
  await tiaRequest("/booking/package-offers", {
    method: "PUT",
    body: JSON.stringify({
      service_id: serviceId,
      device_key: deviceKey,
      sessions_count: sessionsCount,
      price_minor: moneyMinor(formData.get("price")),
      currency: "EGP",
      is_active: active,
    }),
  });
  revalidatePath("/services");
}