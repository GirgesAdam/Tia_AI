"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { createService } from "./actions";

export function ServiceCreateForm() {
  const [requiresLaserDevice, setRequiresLaserDevice] = useState(false);

  return (
    <form action={createService} className="grid gap-3 md:grid-cols-2 xl:grid-cols-6 xl:items-end">
      <label className="xl:col-span-2">
        <span className="mb-1.5 block text-xs font-bold">اسم الخدمة</span>
        <Input name="name" required maxLength={200} placeholder="مثال: Full Body" />
      </label>
      <label>
        <span className="mb-1.5 block text-xs font-bold">التصنيف</span>
        <Input name="category" maxLength={120} placeholder="مثال: Laser" />
      </label>
      <label>
        <span className="mb-1.5 block text-xs font-bold">المدة بالدقائق</span>
        <Input name="duration_minutes" type="number" min="1" max="1440" defaultValue="60" required />
      </label>

      <label className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700">
        <input
          type="checkbox"
          name="requires_laser_device"
          value="1"
          checked={requiresLaserDevice}
          onChange={(event) => setRequiresLaserDevice(event.target.checked)}
        />
        يحتاج تحديد جهاز ليزر
      </label>

      <div className="xl:row-span-2">
        <Button type="submit" className="w-full">إضافة</Button>
      </div>

      {requiresLaserDevice ? (
        <div className="grid gap-3 md:col-span-2 md:grid-cols-2 xl:col-span-5">
          <label>
            <span className="mb-1.5 block text-xs font-bold">سعر Prime Lase</span>
            <Input
              name="prime_lase_price"
              type="number"
              min="0"
              step="0.01"
              required
              placeholder="سعر الجلسة"
            />
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-bold">سعر Candela Gentle</span>
            <Input
              name="candela_gentle_price"
              type="number"
              min="0"
              step="0.01"
              required
              placeholder="سعر الجلسة"
            />
          </label>
        </div>
      ) : (
        <label className="md:col-span-2 xl:col-span-5">
          <span className="mb-1.5 block text-xs font-bold">السعر الأساسي</span>
          <Input name="price" type="number" min="0" step="0.01" defaultValue="0" required />
        </label>
      )}
    </form>
  );
}
