import { Banknote, CalendarRange, Pencil, Plus, Trash2, TrendingDown, TrendingUp, WalletCards } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatMoney } from "@/lib/format";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";

import { createExpense, deleteExpense, updateExpense } from "./actions";

type ExpenseCategory =
  | "rent"
  | "payroll"
  | "supplies"
  | "marketing"
  | "utilities"
  | "maintenance"
  | "software"
  | "taxes"
  | "other";

type Expense = {
  id: string;
  title: string;
  category: ExpenseCategory;
  amount_minor: number;
  currency: string;
  incurred_on: string;
  note: string | null;
  created_at: string;
  updated_at: string;
};

type ProfitabilityCurrency = {
  currency: string;
  gross_payments_minor: number;
  refunds_minor: number;
  net_revenue_minor: number;
  expenses_minor: number;
  profit_minor: number;
};

type Profitability = {
  start_date: string;
  end_date: string;
  currencies: ProfitabilityCurrency[];
};

type SearchParams = { start_date?: string; end_date?: string };

const categoryLabels: Record<ExpenseCategory, string> = {
  rent: "إيجار",
  payroll: "رواتب",
  supplies: "مستلزمات",
  marketing: "تسويق",
  utilities: "مرافق",
  maintenance: "صيانة",
  software: "برامج واشتراكات",
  taxes: "ضرائب ورسوم",
  other: "أخرى",
};

const categories = Object.entries(categoryLabels) as Array<[ExpenseCategory, string]>;

function validDate(value: string | undefined) {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}

function amountInputValue(minor: number) {
  return (minor / 100).toFixed(minor % 100 === 0 ? 0 : 2);
}

function ProfitCard({ item }: { item: ProfitabilityCurrency }) {
  const profitable = item.profit_minor >= 0;
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <div>
          <CardTitle>{item.currency}</CardTitle>
          <p className="mt-1 text-xs font-semibold text-[var(--muted)]">التحصيل والمصروفات خلال الفترة المحددة</p>
        </div>
        <span className={`grid size-10 place-items-center rounded-xl ${profitable ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>
          {profitable ? <TrendingUp size={19} /> : <TrendingDown size={19} />}
        </span>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-[11px] font-bold text-slate-500">المدفوعات</div>
            <div className="mt-1 text-lg font-black text-slate-950">{formatMoney(item.gross_payments_minor, item.currency)}</div>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-[11px] font-bold text-slate-500">المرتجعات</div>
            <div className="mt-1 text-lg font-black text-slate-950">{formatMoney(item.refunds_minor, item.currency)}</div>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-[11px] font-bold text-slate-500">المصروفات</div>
            <div className="mt-1 text-lg font-black text-slate-950">{formatMoney(item.expenses_minor, item.currency)}</div>
          </div>
          <div className={`rounded-xl p-3 ${profitable ? "bg-emerald-50" : "bg-rose-50"}`}>
            <div className={`text-[11px] font-bold ${profitable ? "text-emerald-700" : "text-rose-700"}`}>صافي الربح</div>
            <div className={`mt-1 text-lg font-black ${profitable ? "text-emerald-950" : "text-rose-950"}`}>{formatMoney(item.profit_minor, item.currency)}</div>
          </div>
        </div>
        <div className="mt-3 text-xs font-semibold text-[var(--muted)]">
          صافي الإيراد بعد المرتجعات: {formatMoney(item.net_revenue_minor, item.currency)}
        </div>
      </CardContent>
    </Card>
  );
}

function ExpenseFields({ expense, defaultDate }: { expense?: Expense; defaultDate: string }) {
  return (
    <>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <label className="xl:col-span-2">
          <span className="mb-1.5 block text-xs font-bold text-slate-600">المصروف</span>
          <Input name="title" required maxLength={200} defaultValue={expense?.title || ""} placeholder="مثال: إيجار فرع التجمع" />
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">التصنيف</span>
          <Select name="category" defaultValue={expense?.category || "other"}>
            {categories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </Select>
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">المبلغ</span>
          <Input name="amount" type="number" min="0.01" step="0.01" required defaultValue={expense ? amountInputValue(expense.amount_minor) : ""} placeholder="0.00" />
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">العملة</span>
          <Input name="currency" required minLength={3} maxLength={3} defaultValue={expense?.currency || "EGP"} className="uppercase" />
        </label>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[220px_minmax(0,1fr)]">
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">تاريخ المصروف</span>
          <Input name="incurred_on" type="date" required defaultValue={expense?.incurred_on || defaultDate} />
        </label>
        <label>
          <span className="mb-1.5 block text-xs font-bold text-slate-600">ملاحظة اختيارية</span>
          <Textarea name="note" maxLength={1000} defaultValue={expense?.note || ""} rows={2} placeholder="أي تفاصيل تساعد في المراجعة لاحقًا" />
        </label>
      </div>
    </>
  );
}

export default async function FinancePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const raw = await searchParams;
  const startDate = validDate(raw.start_date);
  const endDate = validDate(raw.end_date);
  const { workspace } = await getAppContext();
  const isAdmin = workspace.role === "admin";

  const profitQuery = new URLSearchParams();
  if (startDate) profitQuery.set("start_date", startDate);
  if (endDate) profitQuery.set("end_date", endDate);
  const profitability = await tiaRequest<Profitability>(`/finance/profitability${profitQuery.size ? `?${profitQuery.toString()}` : ""}`);

  const expenseQuery = new URLSearchParams({
    start_date: profitability.start_date,
    end_date: profitability.end_date,
    limit: "500",
  });
  const expenses = await tiaRequest<Expense[]>(`/finance/expenses?${expenseQuery.toString()}`);

  return (
    <>
      <PageHeader
        title="المالية"
        description="تابع التحصيل الفعلي والمرتجعات والمصروفات وصافي الربح من بيانات Tia الحقيقية، بدون تقدير الإيراد من أسعار المواعيد."
      />

      <Card className="mb-5">
        <CardContent className="pt-5">
          <form method="GET" className="flex flex-wrap items-end gap-3">
            <label>
              <span className="mb-1.5 block text-xs font-bold text-slate-600">من</span>
              <Input name="start_date" type="date" max={profitability.end_date} defaultValue={profitability.start_date} />
            </label>
            <label>
              <span className="mb-1.5 block text-xs font-bold text-slate-600">إلى</span>
              <Input name="end_date" type="date" min={profitability.start_date} defaultValue={profitability.end_date} />
            </label>
            <Button type="submit" variant="outline"><CalendarRange size={16} />تطبيق الفترة</Button>
            <div className="mr-auto text-xs font-semibold text-[var(--muted)]">{expenses.length.toLocaleString("ar-EG")} مصروف في الفترة</div>
          </form>
        </CardContent>
      </Card>

      <div className="mb-5 grid gap-4">
        {profitability.currencies.length ? profitability.currencies.map((item) => <ProfitCard key={item.currency} item={item} />) : (
          <Card>
            <CardContent className="py-10 text-center">
              <WalletCards className="mx-auto text-slate-300" size={34} />
              <div className="mt-3 font-black text-slate-900">لا توجد حركة مالية في هذه الفترة</div>
              <p className="mt-1 text-sm text-[var(--muted)]">ستظهر المدفوعات والمرتجعات والمصروفات هنا بمجرد تسجيلها.</p>
            </CardContent>
          </Card>
        )}
      </div>

      {isAdmin && (
        <Card className="mb-5">
          <CardHeader className="flex-row items-center justify-between gap-3">
            <div>
              <CardTitle>إضافة مصروف</CardTitle>
              <p className="mt-1 text-xs text-[var(--muted)]">سجّل المصروف وقت حدوثه ليظهر فورًا في حساب الربحية.</p>
            </div>
            <span className="grid size-9 place-items-center rounded-xl bg-teal-50 text-teal-700"><Plus size={17} /></span>
          </CardHeader>
          <CardContent>
            <form action={createExpense}>
              <ExpenseFields defaultDate={profitability.end_date} />
              <div className="mt-4 flex justify-end"><Button type="submit"><Plus size={16} />إضافة المصروف</Button></div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div>
            <CardTitle>المصروفات</CardTitle>
            <p className="mt-1 text-xs text-[var(--muted)]">المصروفات المسجلة بين {profitability.start_date} و{profitability.end_date}.</p>
          </div>
          <span className="grid size-9 place-items-center rounded-xl bg-slate-100 text-slate-600"><Banknote size={17} /></span>
        </CardHeader>
        <CardContent>
          {expenses.length ? (
            <div className="space-y-3">
              {expenses.map((expense) => (
                <div key={expense.id} className="rounded-2xl border border-[var(--border)] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="font-black text-slate-950">{expense.title}</div>
                      <div className="mt-1 text-xs font-semibold text-[var(--muted)]">{categoryLabels[expense.category]} · {expense.incurred_on}</div>
                      {expense.note && <div className="mt-2 text-sm text-slate-600">{expense.note}</div>}
                    </div>
                    <div className="text-left text-lg font-black text-slate-950">{formatMoney(expense.amount_minor, expense.currency)}</div>
                  </div>

                  {isAdmin && (
                    <div className="mt-3 border-t border-slate-100 pt-3">
                      <details>
                        <summary className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-bold text-teal-700 hover:text-teal-800">
                          <Pencil size={14} /> تعديل المصروف
                        </summary>
                        <form action={updateExpense} className="mt-4 rounded-xl bg-slate-50 p-4">
                          <input type="hidden" name="expense_id" value={expense.id} />
                          <ExpenseFields expense={expense} defaultDate={profitability.end_date} />
                          <div className="mt-4 flex flex-wrap justify-end gap-2">
                            <Button type="submit" size="sm"><Pencil size={14} />حفظ التعديل</Button>
                          </div>
                        </form>
                      </details>
                      <details className="mt-2">
                        <summary className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-bold text-rose-700 hover:text-rose-800">
                          <Trash2 size={14} /> حذف المصروف
                        </summary>
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-rose-50 p-3">
                          <span className="text-xs font-semibold text-rose-900">الحذف نهائي ولن يدخل هذا المصروف في حساب الربحية بعد ذلك.</span>
                          <form action={deleteExpense}>
                            <input type="hidden" name="expense_id" value={expense.id} />
                            <Button type="submit" size="sm" variant="danger"><Trash2 size={14} />تأكيد الحذف</Button>
                          </form>
                        </div>
                      </details>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-[var(--muted)]">
              لا توجد مصروفات مسجلة في هذه الفترة.
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
