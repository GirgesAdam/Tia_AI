import { Cpu, PackageCheck, PackagePlus, Save } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatMoney } from "@/lib/format";
import type { PulseBillingSettings, PulsePackOffer } from "@/lib/types";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";

import { updatePackageOffer } from "./actions";
import { PulsePricingPanel } from "./pulse-pricing-panel";
import { ServiceCreateForm } from "./service-create-form";
import { ServicePricingForm } from "./service-pricing-form";

type Service = {
  id: string;
  name: string;
  category: string | null;
  operational_category: "laser" | "dermatology" | "slimming";
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
  duration_minutes: number | null;
  currency: string;
  configured: boolean;
};
type PackageOffer = {
  id: string;
  service_id: string;
  service_name: string;
  device_key: "prime_lase" | "candela_gentle";
  device_name: string;
  sessions_count: 3 | 6 | 9;
  price_minor: number;
  currency: string;
  is_active: boolean;
  standalone_session_price_minor: number;
  savings_minor: number;
};

function categoryLabel(value: Service["operational_category"]) {
  return value === "laser" ? "ليزر" : value === "slimming" ? "تخسيس" : "جلدية";
}

function major(minor: number | null) {
  return minor == null ? "" : String(minor / 100);
}

export default async function ServicesPage() {
  const [{ workspace }, services, devicePrices, packageOffers, pulseSettings, pulseOffers] = await Promise.all([
    getAppContext(),
    tiaRequest<Service[]>("/clinic/services"),
    tiaRequest<DevicePrice[]>("/inventory/laser-prices").catch(() => []),
    tiaRequest<PackageOffer[]>("/booking/package-offers").catch(() => []),
    tiaRequest<PulseBillingSettings[]>("/booking/pulse-device-prices"),
    tiaRequest<PulsePackOffer[]>("/booking/pulse-pack-offers"),
  ]);
  const isAdmin = workspace.role === "admin";
  const byService = new Map<string, DevicePrice[]>();
  for (const price of devicePrices) byService.set(price.service_id, [...(byService.get(price.service_id) || []), price]);
  const offerByKey = new Map(
    packageOffers.map((offer) => [`${offer.service_id}:${offer.device_key}:${offer.sessions_count}`, offer]),
  );

  return (
    <>
      <PageHeader
        title="الخدمات والأسعار"
        description="أضف الخدمات وعدّل أسعارها ومددها وباقاتها. خدمات الليزر لها إعداد مستقل لكل جهاز، ومن هنا تقدر كمان تسعّر الـPulses وباقاتها."
      />
      {isAdmin && (
        <Card className="mb-5">
          <CardHeader><CardTitle className="flex items-center gap-2"><PackagePlus size={18} /> إضافة خدمة</CardTitle></CardHeader>
          <CardContent>
            <ServiceCreateForm />
            <p className="mt-3 text-xs text-[var(--muted)]">لو الخدمة تحتاج جهاز ليزر، السعر والمدة بيتحددوا لكل جهاز بدل السعر والمدة الأساسيين.</p>
          </CardContent>
        </Card>
      )}

      {isAdmin && (
        <div className="mb-5">
          <PulsePricingPanel settings={pulseSettings} offers={pulseOffers} />
        </div>
      )}

      <div className="space-y-4">
        {services.map((service) => {
          const prices = byService.get(service.id) || [];
          return (
            <Card key={service.id}>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div>
                  <CardTitle>{service.name}</CardTitle>
                  <p className="mt-1 text-xs font-semibold text-[var(--muted)]">{categoryLabel(service.operational_category)} · {service.requires_laser_device ? "المدة حسب الجهاز" : `${service.duration_minutes} دقيقة`}</p>
                </div>
                <span className="text-sm font-black text-slate-900">{service.requires_laser_device ? "حسب الجهاز" : formatMoney(service.price_minor, service.currency)}</span>
              </CardHeader>
              <CardContent className="space-y-4">
                {isAdmin ? (
                  <ServicePricingForm service={service} devicePrices={prices} />
                ) : null}

                {service.requires_laser_device && (
                  <div className="grid gap-3 lg:grid-cols-2">
                    {(["prime_lase", "candela_gentle"] as const).map((deviceKey) => {
                      const row = prices.find((item) => item.device_key === deviceKey);
                      const name = deviceKey === "prime_lase" ? "Prime Lase" : "Candela Gentle";
                      const configured = Boolean(row?.configured && row.price_minor != null);
                      return (
                        <div key={deviceKey} className="rounded-2xl border border-slate-200 p-4">
                          <div className="mb-3 flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 font-black text-slate-900"><Cpu size={16} /> {name}</div>
                            {configured && row?.price_minor != null && <span className="text-xs font-black text-teal-800">{formatMoney(row.price_minor, row.currency)}</span>}
                          </div>
                          {configured && row?.duration_minutes ? (
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div className="rounded-lg bg-slate-50 p-2"><span className="text-slate-500">السعر</span><b className="mt-1 block">{row.price_minor != null ? formatMoney(row.price_minor, row.currency) : "—"}</b></div>
                              <div className="rounded-lg bg-slate-50 p-2"><span className="text-slate-500">المدة</span><b className="mt-1 block">{row.duration_minutes} دقيقة</b></div>
                            </div>
                          ) : (
                            <div className="rounded-xl bg-amber-50 p-3 text-xs font-semibold text-amber-900">حدد السعر والمدة لهذا الجهاز من إعدادات الخدمة أعلاه.</div>
                          )}

                          <div className="mt-4 border-t border-slate-100 pt-4">
                            <div className="mb-3 flex items-center gap-2 text-sm font-black text-slate-900"><PackageCheck size={16} /> الباكيدجات</div>
                            {!configured ? (
                              <div className="rounded-xl bg-amber-50 p-3 text-xs font-semibold text-amber-900">حدد سعر الجلسة على الجهاز أولًا قبل تفعيل باكيدجاته.</div>
                            ) : (
                              <div className="space-y-2">
                                {([3, 6, 9] as const).map((sessionsCount) => {
                                  const offer = offerByKey.get(`${service.id}:${deviceKey}:${sessionsCount}`);
                                  return isAdmin ? (
                                    <form key={sessionsCount} action={updatePackageOffer} className="grid grid-cols-[78px_minmax(120px,1fr)_auto] items-end gap-2 rounded-xl bg-slate-50 p-3">
                                      <input type="hidden" name="service_id" value={service.id} />
                                      <input type="hidden" name="device_key" value={deviceKey} />
                                      <input type="hidden" name="sessions_count" value={sessionsCount} />
                                      <label className="flex h-10 items-center gap-2 text-xs font-black"><input type="checkbox" name="is_active" value="1" defaultChecked={offer?.is_active ?? false} /> {sessionsCount} جلسات</label>
                                      <label><span className="mb-1 block text-[11px] font-bold text-slate-600">سعر الباكيدج</span><Input name="price" type="number" min="0" step="0.01" required defaultValue={offer ? major(offer.price_minor) : ""} placeholder="السعر الإجمالي" /></label>
                                      <Button type="submit" size="sm" variant="outline"><Save size={13} /> حفظ</Button>
                                      {offer?.is_active && (
                                        <div className="col-span-3 text-[11px] font-semibold text-slate-500">
                                          {offer.savings_minor > 0 ? `توفير ${formatMoney(offer.savings_minor, offer.currency)} مقارنة بـ ${sessionsCount} جلسات منفصلة.` : "لا يوجد خصم مقارنة بسعر الجلسات المنفصلة."}
                                        </div>
                                      )}
                                    </form>
                                  ) : offer?.is_active ? (
                                    <div key={sessionsCount} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm">
                                      <b>{sessionsCount} جلسات</b><span>{formatMoney(offer.price_minor, offer.currency)}</span>
                                    </div>
                                  ) : null;
                                })}
                              </div>
                            )}
                          </div>
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
