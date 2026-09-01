import Link from "next/link";
import { Bookmark, Megaphone } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { tiaRequest } from "@/lib/tia/api";
import type { AnalyticsCatalog, AnalyticsSavedView, CRMCohort } from "@/lib/types";
import { AnalyticsCatalogPanel } from "./catalog";

export default async function AnalyticsPage() {
  const [cohorts, catalog, savedViews] = await Promise.all([
    tiaRequest<CRMCohort[]>("/crm/cohorts?limit=8"),
    tiaRequest<AnalyticsCatalog>("/analytics/catalog"),
    tiaRequest<AnalyticsSavedView[]>("/analytics/views?limit=20"),
  ]);

  return (
    <>
      <PageHeader
        title="التقارير والتحليلات"
        description="اختر التقرير الذي تحتاجه وحدد الفترة أو الفئة، وستظهر النتيجة في رسم أو جدول واضح قابل للحفظ والتصدير."
        action={<Link href="/analytics/campaigns" className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm font-bold"><Megaphone size={16}/>أداء الحملات</Link>}
      />

      <AnalyticsCatalogPanel catalog={catalog} savedViews={savedViews} />

      <Card className="mb-5">
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div>
            <CardTitle>مجموعات العملاء المحفوظة</CardTitle>
            <p className="mt-1 text-xs text-[var(--muted)]">قوائم حفظتها من تحليلات العملاء لاستخدامها في المتابعة أو الحملات.</p>
          </div>
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Bookmark size={17} /></span>
        </CardHeader>
        <CardContent>
          {cohorts.length ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {cohorts.map(cohort => (
                <Link key={cohort.id} href={`/analytics/cohorts/${cohort.id}`} className="rounded-2xl border border-[var(--border)] p-3 transition hover:border-teal-300 hover:bg-teal-50/30">
                  <div className="font-black">{cohort.name}</div>
                  <div className="mt-1 text-xs text-[var(--muted)]">{cohort.member_count.toLocaleString("ar-EG")} عميل · {cohort.period_label}</div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-[var(--muted)]">
              لا توجد مجموعات محفوظة بعد. يمكنك حفظ أي نتيجة تحتوي على قائمة عملاء لاستخدامها لاحقًا في المتابعة أو الحملات.
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
