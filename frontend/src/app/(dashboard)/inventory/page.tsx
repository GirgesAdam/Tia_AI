import { PackagePlus, ShoppingBag, Syringe } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";

import { addInventoryStock, createClinicProduct, createInventoryItem, recordInventoryUsage, updateClinicProductQuantity } from "./actions";

type Item = {
  id: string;
  name: string;
  quantity_ml: number | string;
  low_stock_threshold_ml: number | string | null;
  notes: string | null;
};

type Product = {
  id: string;
  name: string;
  description: string | null;
  quantity_on_hand: number;
  is_active: boolean;
};

export default async function InventoryPage() {
  const [{ workspace }, items, products] = await Promise.all([
    getAppContext(),
    tiaRequest<Item[]>("/inventory/items"),
    tiaRequest<Product[]>("/inventory/products").catch(() => []),
  ]);
  const isAdmin = workspace.role === "admin";

  return (
    <>
      <PageHeader title="المخزن" description="تابع كميات المنتجات والحقن بشكل مباشر، وسجّل الإضافة والاستخدام بدون حقول طبية غير لازمة للاستقبال." />

      <Card className="mb-5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><ShoppingBag size={18} /> منتجات العيادة</CardTitle>
          <p className="mt-1 text-xs text-[var(--muted)]">العدد هنا هو رصيد المخزن الحالي، ويقل تلقائيًا عند إضافة منتج لموعد ويرجع عند حذف المنتج من الموعد.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          {isAdmin && (
            <form action={createClinicProduct} className="grid gap-3 md:grid-cols-[minmax(180px,1fr)_minmax(220px,2fr)_120px_auto] md:items-end">
              <label><span className="mb-1.5 block text-xs font-bold">اسم المنتج</span><Input name="name" required maxLength={180} placeholder="مثال: Skin Protector" /></label>
              <label><span className="mb-1.5 block text-xs font-bold">وصف اختياري</span><Input name="description" maxLength={500} placeholder="معلومة قصيرة للاستقبال" /></label>
              <label><span className="mb-1.5 block text-xs font-bold">العدد</span><Input name="quantity_on_hand" type="number" min="0" step="1" defaultValue="0" required /></label>
              <Button type="submit"><PackagePlus size={15} /> إضافة المنتج</Button>
            </form>
          )}
          {products.length ? (
            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="data-table min-w-[620px]">
                <thead><tr><th>المنتج</th><th>الوصف</th><th>العدد المتاح</th><th>تعديل الرصيد</th></tr></thead>
                <tbody>{products.map((product) => <tr key={product.id}><td className="font-black">{product.name}</td><td>{product.description || "—"}</td><td className="font-black">{product.quantity_on_hand.toLocaleString("ar-EG")}</td><td>{isAdmin ? <form action={updateClinicProductQuantity} className="flex items-center gap-2"><input type="hidden" name="product_id" value={product.id} /><Input name="quantity_on_hand" type="number" min="0" step="1" required defaultValue={product.quantity_on_hand} className="w-24" /><Button size="sm" variant="outline">حفظ</Button></form> : "—"}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-[var(--muted)]">لا توجد منتجات بعد.</div>}
        </CardContent>
      </Card>

      {isAdmin && (
        <Card className="mb-5">
          <CardHeader><CardTitle className="flex items-center gap-2"><PackagePlus size={18} /> إضافة حقنة للمخزن</CardTitle></CardHeader>
          <CardContent>
            <form action={createInventoryItem} className="grid gap-3 md:grid-cols-3">
              <label><span className="mb-1.5 block text-xs font-bold">الاسم</span><Input name="name" required placeholder="مثال: Botox vial" /></label>
              <label><span className="mb-1.5 block text-xs font-bold">الكمية الحالية mL</span><Input name="quantity_ml" type="number" min="0" step="0.001" required /></label>
              <label><span className="mb-1.5 block text-xs font-bold">تنبيه المخزون عند mL</span><Input name="low_stock_threshold_ml" type="number" min="0" step="0.001" /></label>
              <label className="md:col-span-2"><span className="mb-1.5 block text-xs font-bold">ملاحظة</span><Textarea name="notes" rows={2} /></label>
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
                <div><CardTitle className="flex items-center gap-2"><Syringe size={17} />{item.name}</CardTitle></div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${low ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700"}`}>{low ? "مخزون منخفض" : "متاح"}</span>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-xl bg-slate-50 p-3"><div className="text-[11px] font-bold text-slate-500">المتبقي</div><div className="mt-1 text-xl font-black">{quantityMl.toLocaleString("ar-EG")} mL</div></div>
                {isAdmin && <div className="grid gap-3 sm:grid-cols-2">
                  <form action={addInventoryStock} className="rounded-xl border p-3"><input type="hidden" name="item_id" value={item.id} /><div className="text-xs font-black">إضافة كمية</div><div className="mt-2 flex gap-2"><Input name="quantity_ml" type="number" min="0.001" step="0.001" required placeholder="mL" /><Button size="sm" variant="outline">إضافة</Button></div></form>
                  <form action={recordInventoryUsage} className="rounded-xl border p-3"><input type="hidden" name="item_id" value={item.id} /><div className="text-xs font-black">تسجيل استخدام</div><div className="mt-2 flex gap-2"><Input name="used_ml" type="number" min="0.001" step="0.001" required placeholder="mL مستخدمة" /><Button size="sm">خصم</Button></div></form>
                </div>}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </>
  );
}
