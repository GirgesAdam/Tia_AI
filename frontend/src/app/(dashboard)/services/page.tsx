import { CircleDollarSign, Cpu, PackagePlus, Save } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatMoney } from "@/lib/format";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";

import { createService, updateLaserDevicePrice, updateServicePricing } from "./actions";

type Service = {
  id: string;
  name: string;
  category: string | null;
  duration_minutes: number;
  price_minor: number;
  currency: string;
  requires_laser_device: boolean;
  is_active: boolean;
};
type DevicePrice = {
  service_id: string;
  device_key: "prime_lase" | "candela_gentle";
  device_name: string;
  price_minor: number | null;
  currency: string;
  configured: boolean;
};

function major(minor: number | null) {
  return minor == null ? "" : String(minor / 100);
}

export default async function ServicesPage() {
  const [{ workspace }, services, devicePrices] = await Promise.all([
    getAppContext(),
    tiaRequest<Service[]>("/clinic/services"),
    tiaRequest<DevicePrice[]>("/inventory/laser-prices").catch(() => []),
  ]);
  const isAdmin = workspace.role === "admin";
  const byService = new Map<string, DevicePrice[]>();
  for (const price of devicePrices) byService.set(price.service_id, [...(byService.get(price.service_id) || []), price]);

  return (
    <>
      <PageHeader title="الخدمات والأسعار" description="أضف الخدمات وعدّل أسماءها وأسعارها. الخدمات التي تحتاج جهاز ليزر لها سعر مستقل لكل جهاز." />
      {isAdmin && (
        <Card className="mb-5">
          <CardHeader><CardTitle className="flex items-center gap-2"><PackagePlus size={18} /> إضافة خدمة</CardTitle></CardHeader>
          <CardContent>
            <form action={createService} className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(180px,1.5fr)_minmax(140px,1fr)_120px_150px_auto] xl:items-end">
              <label><span className="mb-1.5 block text-xs font-bold">اسم الخدمة</span><Input name="name" required maxLength={200} placeholder="مثال: Full Body" /></label>
              <label><span className="mb-1.5 block text-xs font-bold">التصنيف</span><Input name="category" maxLength={120} placeholder="مثال: Laser" /></label>
              <label><span className="mb-1.5 block text-xs font-bold">المدة بالدقائق</span><Input name="duration_minutes" type="number" min="1" max="1440" defaultValue="60" required /></label>
              <label><span className="mb-1.5 block text-xs font-bold">السعر الأساسي</span><Input name="price" type="number" min="0" step="0.01" defaultValue="0" required /></label>
              <div className="space-y-2"><label className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700"><input type="checkbox" name="requires_laser_device" value="1" /> يحتاج جهاز ليزر</label><Button type="submit" className="w-full">إضافة</Button></div>
            </form>
            <p className="mt-3 text-xs text-[var(--muted)]">لو الخدمة تحتاج جهاز ليزر، السعر الأساسي لا يُستخدم في الحجز؛ حدّد سعر كل جهاز بعد إضافة الخدمة.</p>
          </CardContent>
        </Card>
      )}
      <div className="space-y-4">
        {services.map((service) => {
          const prices = byService.get(service.id) || [];
          return (
            <Card key={service.id}>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div>
                  <CardTitle>{service.name}</CardTitle>
                  <p className="mt-1 text-xs font-semibold text-[var(--muted)]">{service.category || "بدون تصنيف"} · {service.duration_minutes} دقيقة</p>
                </div>
                <span className="text-sm font-black text-slate-900">{service.requires_laser_device ? "حسب الجهاز" : formatMoney(service.price_minor, service.currency)}</span>
              </CardHeader>
              <CardContent className="space-y-4">
                {isAdmin ? (
                  <form action={updateServicePricing} className="grid gap-3 rounded-xl bg-slate-50 p-3 md:grid-cols-[minmax(180px,1.5fr)_minmax(150px,1fr)_auto_auto] md:items-end">
                    <input type="hidden" name="service_id" value={service.id} />
                    <label><span className="mb-1.5 block text-xs font-bold text-slate-600">اسم الخدمة</span><Input name="name" required maxLength={200} defaultValue={service.name} /></label>
                    <label><span className="mb-1.5 block text-xs font-bold text-slate-600">السعر الأساسي بالجنيه</span><Input name="price" type="number" min="0" step="0.01" required defaultValue={major(service.price_minor)} disabled={service.requires_laser_device} /></label>
                    <label className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700"><input type="checkbox" name="requires_laser_device" value="1" defaultChecked={service.requires_laser_device} /> خدمة تحتاج اختيار جهاز ليزر</label>
                    <Button type="submit" size="sm"><Save size={14} /> حفظ</Button>
                  </form>
                ) : null}

                {service.requires_laser_device && (
                  <div className="grid gap-3 md:grid-cols-2">
                    {(["prime_lase", "candela_gentle"] as const).map((deviceKey) => {
                      const row = prices.find((item) => item.device_key === deviceKey);
                      const name = deviceKey === "prime_lase" ? "Prime Lase" : "Candela Gentle";
                      return (
                        <div key={deviceKey} className="rounded-xl border border-slate-200 p-3">
                          <div className="mb-3 flex items-center gap-2 font-black text-slate-900"><Cpu size={16} /> {name}</div>
                          {isAdmin ? (
                            <form action={updateLaserDevicePrice} className="flex items-end gap-2">
                              <input type="hidden" name="service_id" value={service.id} />
                              <input type="hidden" name="device_key" value={deviceKey} />
                              <label className="min-w-0 flex-1"><span className="mb-1.5 block text-xs font-bold text-slate-600">سعر الجلسة بهذا الجهاز</span><Input name="price" type="number" min="0" step="0.01" required defaultValue={major(row?.price_minor ?? null)} placeholder="حدد السعر" /></label>
                              <Button type="submit" size="sm" variant="outline"><CircleDollarSign size={14} /> حفظ</Button>
                            </form>
                          ) : <div className="font-black">{row?.configured && row.price_minor != null ? formatMoney(row.price_minor, row.currency) : "غير محدد"}</div>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </>
  );
}
