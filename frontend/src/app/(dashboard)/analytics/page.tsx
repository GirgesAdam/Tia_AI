import Link from "next/link";
import { Bookmark, CalendarCheck2, ContactRound, Megaphone, Percent, WalletCards } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";
import { tiaRequest } from "@/lib/tia/api";
import type { AnalyticsCatalog, AnalyticsSavedView, CRMCohort } from "@/lib/types";
import { AnalyticsCatalogPanel } from "./catalog";

type AnalyticsMoney = {
  currency: string;
  completed_value_minor: number;
  gross_paid_minor: number;
  refunded_minor: number;
  recorded_paid_minor: number;
  outstanding_balance_minor: number;
};

type AnalyticsBreakdown = {
  id: string;
  name: string;
  appointments: number;
  completed: number;
  no_show: number;
  cancelled: number;
};

type AnalyticsDaily = {
  date: string;
  appointments: number;
  completed: number;
  no_show: number;
  cancelled: number;
  new_patients: number;
};

type AnalyticsOverview = {
  days: number;
  total_appointments: number;
  completed_appointments: number;
  no_show_appointments: number;
  cancelled_appointments: number;
  attendance_rate_percent: number;
  no_show_rate_percent: number;
  cancellation_rate_percent: number;
  new_patients: number;
  conversations_started: number;
  handoffs_created: number;
  money: AnalyticsMoney[];
  top_services: AnalyticsBreakdown[];
  daily: AnalyticsDaily[];
};

function percent(value: number) {
  return `${Math.round(value * 10) / 10}%`;
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("ar-EG", { day: "numeric", month: "short" }).format(new Date(`${value}T12:00:00`));
}

export default async function AnalyticsPage() {
  const [overview, cohorts, catalog, savedViews] = await Promise.all([
    tiaRequest<AnalyticsOverview>("/analytics/overview?days=30"),
    tiaRequest<CRMCohort[]>("/crm/cohorts?limit=8"),
    tiaRequest<AnalyticsCatalog>("/analytics/catalog"),
    tiaRequest<AnalyticsSavedView[]>("/analytics/views?limit=20"),
  ]);
  const primaryMoney = overview.money[0];
  const recentDays = overview.daily.slice(-7);

  return (
    <>
      <PageHeader
        title="التقارير والتحليلات"
        description="ملخص أداء العيادة أولًا، وبعده التقارير التفصيلية التي تقدر تشغلها وتحفظها وقت ما تحتاج."
        action={<Link href="/analytics/campaigns" className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm font-bold"><Megaphone size={16}/>أداء الحملات</Link>}
      />

      <section className="mb-7">
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-black text-slate-950">ملخص آخر 30 يوم</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">أهم مؤشرات الحجز والحضور والعملاء والتحصيل.</p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="إجمالي المواعيد" value={overview.total_appointments} detail={`${overview.completed_appointments} موعد مكتمل`} icon={CalendarCheck2} />
          <StatCard label="نسبة الحضور" value={percent(overview.attendance_rate_percent)} detail={`${overview.no_show_appointments} عدم حضور · ${overview.cancelled_appointments} إلغاء`} icon={Percent} />
          <StatCard label="عملاء جدد" value={overview.new_patients} detail={`${overview.conversations_started} محادثة بدأت خلال الفترة`} icon={ContactRound} />
          <StatCard
            label="المبالغ المحصلة"
            value={primaryMoney ? formatMoney(primaryMoney.recorded_paid_minor, primaryMoney.currency) : "—"}
            detail={primaryMoney ? `المتبقي ${formatMoney(primaryMoney.outstanding_balance_minor, primaryMoney.currency)}` : "لا توجد حركة مالية مسجلة"}
            icon={WalletCards}
          />
        </div>

        <div className="mt-5 grid gap-5 xl:grid-cols-[1.1fr_.9fr]">
          <Card>
            <CardHeader>
              <CardTitle>حركة آخر 7 أيام</CardTitle>
              <p className="mt-1 text-xs text-[var(--muted)]">المواعيد والعملاء الجدد يومًا بيوم.</p>
            </CardHeader>
            <CardContent className="p-0 pt-0 sm:p-0 sm:pt-0">
              <div className="table-shell border-0">
                <table className="data-table min-w-[560px]">
                  <thead>
                    <tr>
                      <th>اليوم</th>
                      <th>المواعيد</th>
                      <th>مكتملة</th>
                      <th>عدم حضور</th>
                      <th>عملاء جدد</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentDays.map((day) => (
                      <tr key={day.date}>
                        <td className="font-bold">{shortDate(day.date)}</td>
                        <td>{day.appointments}</td>
                        <td>{day.completed}</td>
                        <td>{day.no_show}</td>
                        <td>{day.new_patients}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>أكثر الخدمات حجزًا</CardTitle>
              <p className="mt-1 text-xs text-[var(--muted)]">أعلى الخدمات حسب عدد المواعيد خلال آخر 30 يوم.</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {overview.top_services.slice(0, 6).map((service, index) => (
                <div key={service.id} className="flex items-center justify-between gap-4 rounded-xl bg-slate-50 px-3 py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-bold text-slate-900">{index + 1}. {service.name}</div>
                    <div className="mt-0.5 text-[11px] text-[var(--muted)]">{service.completed} مكتملة · {service.no_show} عدم حضور</div>
                  </div>
                  <div className="shrink-0 text-lg font-black text-slate-900">{service.appointments}</div>
                </div>
              ))}
              {!overview.top_services.length && <div className="py-6 text-center text-sm text-[var(--muted)]">لا توجد بيانات كافية للفترة الحالية.</div>}
            </CardContent>
          </Card>
        </div>
      </section>

      <section>
        <div className="mb-3">
          <h2 className="text-lg font-black text-slate-950">التقارير التفصيلية</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">اختر التقرير والفترة أو الفئة المطلوبة، وستظهر النتيجة من الحسابات الموثوقة داخل Tia.</p>
        </div>
        <AnalyticsCatalogPanel catalog={catalog} savedViews={savedViews} />
      </section>

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
