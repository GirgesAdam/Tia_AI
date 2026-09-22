"use client";

import { useState } from "react";

import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { updateServicePricing } from "./actions";

type DeviceConfig = {
  device_key: "prime_lase" | "candela_gentle";
  price_minor: number | null;
  duration_minutes: number | null;
};

type ServiceConfig = {
  id: string;
  name: string;
  duration_minutes: number;
  price_minor: number;
  category: "laser" | "dermatology" | "slimming";
  requires_laser_device: boolean;
};

function major(minor: number | null | undefined) {
  return minor == null ? "" : String(minor / 100);
}

export function ServicePricingForm({
  service,
  devicePrices,
}: {
  service: ServiceConfig;
  devicePrices: DeviceConfig[];
}) {
  const [requiresLaserDevice, setRequiresLaserDevice] = useState(service.requires_laser_device);
  const [category, setCategory] = useState(service.category);
  const config = (key: DeviceConfig["device_key"]) =>
    devicePrices.find((item) => item.device_key === key);

  return (
    <form action={updateServicePricing} className="grid gap-3 rounded-xl bg-slate-50 p-3">
      <input type="hidden" name="service_id" value={service.id} />
      <div className="grid gap-3 md:grid-cols-[minmax(180px,1.4fr)_minmax(130px,.7fr)_auto_auto] md:items-end">
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">اسم الخدمة</span>
          <Input name="name" required maxLength={200} defaultValue={service.name} />
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">التصنيف</span>
          {requiresLaserDevice && <input type="hidden" name="category" value="laser" />}
          <select
            name="category"
            value={requiresLaserDevice ? "laser" : category}
            disabled={requiresLaserDevice}
            onChange={(event) => setCategory(event.target.value as typeof category)}
            className="form-control h-10 min-h-10"
          >
            <option value="laser">ليزر</option>
            <option value="dermatology">جلدية</option>
            <option value="slimming">تخسيس</option>
          </select>
        </label>
        <label className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700">
          <input
            type="checkbox"
            name="requires_laser_device"
            value="1"
            checked={requiresLaserDevice}
            onChange={(event) => {
              setRequiresLaserDevice(event.target.checked);
              if (event.target.checked) setCategory("laser");
            }}
          />
          خدمة تحتاج اختيار جهاز ليزر
        </label>
        <Button type="submit" size="sm"><Save size={14} /> حفظ</Button>
      </div>

      {requiresLaserDevice ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {([
            ["prime_lase", "Prime Lase"],
            ["candela_gentle", "Candela Gentle"],
          ] as const).map(([deviceKey, deviceName]) => {
            const row = config(deviceKey);
            return (
              <div key={deviceKey} className="grid gap-3 rounded-xl border border-slate-200 bg-white p-3 sm:grid-cols-2">
                <div className="sm:col-span-2 text-sm font-black text-slate-900">{deviceName}</div>
                <label>
                  <span className="mb-1.5 block text-xs font-bold text-slate-600">سعر الجلسة</span>
                  <Input
                    name={`${deviceKey}_price`}
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    defaultValue={major(row?.price_minor ?? service.price_minor)}
                  />
                </label>
                <label>
                  <span className="mb-1.5 block text-xs font-bold text-slate-600">مدة الجلسة بالدقائق</span>
                  <Input
                    name={`${deviceKey}_duration_minutes`}
                    type="number"
                    min="1"
                    max="1440"
                    required
                    defaultValue={row?.duration_minutes ?? service.duration_minutes}
                  />
                </label>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <label>
            <span className="mb-1.5 block text-xs font-bold text-slate-600">السعر الأساسي بالجنيه</span>
            <Input name="price" type="number" min="0" step="0.01" required defaultValue={major(service.price_minor)} />
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-bold text-slate-600">المدة بالدقائق</span>
            <Input name="duration_minutes" type="number" min="1" max="1440" required defaultValue={service.duration_minutes} />
          </label>
        </div>
      )}
    </form>
  );
}
