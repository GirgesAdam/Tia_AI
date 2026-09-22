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
  const basePriceMinor = requiresLaserDevice ? 0 : moneyMinor(formData.get("price"));
  const baseDurationMinutes = requiresLaserDevice
    ? null
    : positiveInteger(formData.get("duration_minutes"), 60);
  const primeLasePriceMinor = requiresLaserDevice
    ? moneyMinor(formData.get("prime_lase_price"))
    : null;
  const primeLaseDurationMinutes = requiresLaserDevice
    ? positiveInteger(formData.get("prime_lase_duration_minutes"), 60)
    : null;
  const candelaGentlePriceMinor = requiresLaserDevice
    ? moneyMinor(formData.get("candela_gentle_price"))
    : null;
  const candelaGentleDurationMinutes = requiresLaserDevice
    ? positiveInteger(formData.get("candela_gentle_duration_minutes"), 60)
    : null;

  const service = await tiaRequest<{ id: string }>("/clinic/services", {
    method: "POST",
    body: JSON.stringify({
      name,
      slug: `service-${randomUUID()}`,
      category: String(formData.get("category") || "").trim() || null,
      description: null,
      duration_minutes: requiresLaserDevice
        ? (primeLaseDurationMinutes ?? 60)
        : (baseDurationMinutes ?? 60),
      buffer_before_minutes: 0,
      buffer_after_minutes: 0,
      price_minor: requiresLaserDevice ? 0 : basePriceMinor,
      currency: "EGP",
      requires_medical_review: false,
      requires_laser_device: requiresLaserDevice,
    }),
  });

  if (requiresLaserDevice) {
    await Promise.all([
      tiaRequest("/inventory/laser-prices", {
        method: "PUT",
        body: JSON.stringify({
          service_id: service.id,
          device_key: "prime_lase",
          price_minor: primeLasePriceMinor,
          duration_minutes: primeLaseDurationMinutes,
          currency: "EGP",
        }),
      }),
      tiaRequest("/inventory/laser-prices", {
        method: "PUT",
        body: JSON.stringify({
          service_id: service.id,
          device_key: "candela_gentle",
          price_minor: candelaGentlePriceMinor,
          duration_minutes: candelaGentleDurationMinutes,
          currency: "EGP",
        }),
      }),
    ]);
  }

  revalidatePath("/services");
  revalidatePath("/appointments");
}

export async function updateServicePricing(formData: FormData) {
  const serviceId = String(formData.get("service_id") || "");
  const name = String(formData.get("name") || "").trim();
  const requiresLaserDevice = formData.get("requires_laser_device") === "1";
  if (!serviceId || !name) return;

  if (requiresLaserDevice) {
    const primePriceMinor = moneyMinor(formData.get("prime_lase_price"));
    const primeDurationMinutes = positiveInteger(formData.get("prime_lase_duration_minutes"), 60);
    const candelaPriceMinor = moneyMinor(formData.get("candela_gentle_price"));
    const candelaDurationMinutes = positiveInteger(formData.get("candela_gentle_duration_minutes"), 60);

    await tiaRequest(`/clinic/services/${serviceId}`, {
      method: "PATCH",
      body: JSON.stringify({
        name,
        price_minor: 0,
        duration_minutes: primeDurationMinutes,
        requires_laser_device: true,
      }),
    });
    await Promise.all([
      tiaRequest("/inventory/laser-prices", {
        method: "PUT",
        body: JSON.stringify({
          service_id: serviceId,
          device_key: "prime_lase",
          price_minor: primePriceMinor,
          duration_minutes: primeDurationMinutes,
          currency: "EGP",
        }),
      }),
      tiaRequest("/inventory/laser-prices", {
        method: "PUT",
        body: JSON.stringify({
          service_id: serviceId,
          device_key: "candela_gentle",
          price_minor: candelaPriceMinor,
          duration_minutes: candelaDurationMinutes,
          currency: "EGP",
        }),
      }),
    ]);
  } else {
    await tiaRequest(`/clinic/services/${serviceId}`, {
      method: "PATCH",
      body: JSON.stringify({
        name,
        price_minor: moneyMinor(formData.get("price")),
        duration_minutes: positiveInteger(formData.get("duration_minutes"), 60),
        requires_laser_device: false,
      }),
    });
  }

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
      duration_minutes: positiveInteger(formData.get("duration_minutes"), 60),
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
