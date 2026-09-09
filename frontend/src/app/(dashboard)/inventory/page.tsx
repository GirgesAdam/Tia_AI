import { PackagePlus, Syringe } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";

import { addInventoryStock, createInventoryItem, recordInventoryUsage } from "./actions";

type Item = {
  id: string;
  name: string;
  quantity_ml: number | string;
  concentration_mg_per_ml: number | string;
  remaining_mg: number | string;
  low_stock_threshold_ml: number | string | null;
  notes: string | null;
};

export default async function InventoryPage() {
  const [{ workspace }, items] = await Promise.all([
    getAppContext(),
    tiaRequest<Item[]>("/inventory/items"),
  ]);
  const isAdmin = workspace.role === "admin";

  return (
    <>
      <PageHeader title="المخزن" description="تابع الحقن بالملي، وسجّل الاستخدام بالمليجرام. Tia يحول mg إلى mL حسب تركيز كل حقنة ويخصمه من المتبقي." />

      {isAdmin && (
        <Card className="mb-5">
          <CardHeader><CardTitle className="flex items-center gap-2"><PackagePlus size={18} /> إضافة حقنة للمخزن</CardTitle></CardHeader>
          <CardContent>
            <form action={createInventoryItem} className="grid gap-3 md:grid-cols-4">
              <label><span className="mb-1.5 block text-xs font-bold">الاسم</span><Input name="name" required placeholder="مثال: Botox 100U" /></label>
              <label><span className="mb-1.5 block text-xs font-bold">الكمية الحالية mL</span><Input name="quantity_ml" type="number" min="0" step="0.001" required /></label>
              <label><span className="mb-1.5 block text-xs font-bold">التركيز mg/mL</span><Input name="concentration_mg_per_ml" type="number" min="0.001" step="0.001" required /></label>
              <label><span className="mb-1.5 block text-xs font-bold">تنبيه المخزون عند mL</span><Input name="low_stock_threshold_ml" type="number" min="0" step="0.001" /></label>
              <label className="md:col-span-3"><span className="mb-1.5 block text-xs font-bold">ملاحظة</span><Textarea name="notes" rows={2} /></label>
              <div className="flex items-end"><Button type="submit">إضافة</Button></div>
            </form>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {items.map((item) => {
          const quantityMl = Number(item.quantity_ml);
          const threshold = item.low_stock_threshold_ml == null ? null : Number(item.low_stock_threshold_ml);
          const low = threshold != null && quantityMl <= threshold;
          return (
            <Card key={item.id}>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div><CardTitle className="flex items-center gap-2"><Syringe size={17} />{item.name}</CardTitle><p className="mt-1 text-xs text-[var(--muted)]">تركيز {Number(item.concentration_mg_per_ml).toLocaleString("ar-EG")} mg/mL</p></div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${low ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700"}`}>{low ? "مخزون منخفض" : "متاح"}</span>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-slate-50 p-3"><div className="text-[11px] font-bold text-slate-500">المتبقي بالملي</div><div className="mt-1 text-xl font-black">{quantityMl.toLocaleString("ar-EG")} mL</div></div>
                  <div className="rounded-xl bg-slate-50 p-3"><div className="text-[11px] font-bold text-slate-500">المتبقي بالمليجرام</div><div className="mt-1 text-xl font-black">{Number(item.remaining_mg).toLocaleString("ar-EG")} mg</div></div>
                </div>
                {isAdmin && <div className="grid gap-3 sm:grid-cols-2">
                  <form action={addInventoryStock} className="rounded-xl border p-3"><input type="hidden" name="item_id" value={item.id} /><div className="text-xs font-black">إضافة كمية</div><div className="mt-2 flex gap-2"><Input name="quantity_ml" type="number" min="0.001" step="0.001" required placeholder="mL" /><Button size="sm" variant="outline">إضافة</Button></div></form>
                  <form action={recordInventoryUsage} className="rounded-xl border p-3"><input type="hidden" name="item_id" value={item.id} /><div className="text-xs font-black">تسجيل استخدام</div><div className="mt-2 flex gap-2"><Input name="used_mg" type="number" min="0.001" step="0.001" required placeholder="mg مستخدمة" /><Button size="sm">خصم</Button></div><Input className="mt-2" name="appointment_id" placeholder="رقم الموعد (اختياري)" /></form>
                </div>}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </>
  );
}
