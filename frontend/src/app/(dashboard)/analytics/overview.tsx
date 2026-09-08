import { CalendarCheck2, ContactRound, ReceiptText, TrendingUp } from "lucide-react";

import { StatCard } from "@/components/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";
import { tiaRequest } from "@/lib/tia/api";
import type { AnalyticsCatalogRun, AnalyticsCatalogRunRequest } from "@/lib/types";

type Profitability = {
  start_date: string;
  end_date: string;
  currencies: Array<{
    currency: string;
    gross_payments_minor: number;
    refunds_minor: number;
    net_revenue_minor: number;
    expenses_minor: number;
    profit_minor: number;
  }>;
};

function requestFor(analysisKey: string, startDate: string, endDate: string, granularity: "day" | "month" | null = null): AnalyticsCatalogRunRequest {
  return {
    analysis_key: analysisKey,
    lookback_days: null,
    all_history: false,
    start_date: startDate,
    end_date: endDate,
    service_ids: [],
    branch_ids: [],
    doctor_ids: [],
    comparison: false,
    granularity,
    limit: null,
    inactivity_days: null,
    min_visits: null,
    max_visits: null,
    has_future_appointment: null,
    marketing_consent: null,
  };
}

function metricNumber(result: AnalyticsCatalogRun, key: string) {
  const metric = result.rows[0]?.metrics.find((item) => item.key === key);
  return typeof metric?.value === "number" ? metric.value : 0;
}

function RevenueLineChart({ result }: { result: AnalyticsCatalogRun }) {
  const series = result.chart_data.series.find((item) => item.key === "net_paid_minor") || result.chart_data.series[0];
  if (!series || !series.values.length) return <div className="py-16 text-center text-sm text-[var(--muted)]">لا توجد حركة دخل مسجلة في الفترة المختارة.</div>;

  const values = series.values.map((value) => value ?? 0);
  const width = 900;
  const height = 260;
  const padding = 30;
  const min = Math.min(0, ...values);
  const max = Math.max(1, ...values);
  const span = Math.max(1, max - min);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : padding + index * ((width - padding * 2) / (values.length - 1));
    const y = height - padding - ((value - min) / span) * (height - padding * 2);
    return { x, y, value };
  });
  const polyline = points.map((point) => `${point.x},${point.y}`).join(" ");
  const total = values.reduce((sum, value) => sum + value, 0);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--muted)]">
        <span>صافي الدخل = المدفوعات المسجلة ناقص المرتجعات.</span>
        <span className="font-black text-slate-800">إجمالي الفترة: {formatMoney(total, series.currency || "EGP")}</span>
      </div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-64 min-w-[650px] w-full" role="img" aria-label="تطور الدخل خلال الفترة">
          <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} className="stroke-slate-200" />
          <polyline points={polyline} fill="none" className="stroke-teal-700" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
          {points.map((point, index) => (
            <circle key={`${result.chart_data.labels[index]}-${index}`} cx={point.x} cy={point.y} r="4" className="fill-white stroke-teal-700" strokeWidth="3">
              <title>{`${result.chart_data.labels[index] || ""}: ${formatMoney(point.value, series.currency || "EGP")}`}</title>
            </circle>
          ))}
        </svg>
      </div>
      <div className="mt-1 flex justify-between gap-2 text-[10px] text-[var(--muted)]">
        <span>{result.chart_data.labels[0] || "—"}</span>
        <span>{result.chart_data.labels[result.chart_data.labels.length - 1] || "—"}</span>
      </div>
    </div>
  );
}

export async function AnalyticsOverviewPanel({
  startDate,
  endDate,
  periodLabel,
  fullYear,
}: {
  startDate: string;
  endDate: string;
  periodLabel: string;
  fullYear: boolean;
}) {
  const [appointments, newPatients, revenue, profitability] = await Promise.all([
    tiaRequest<AnalyticsCatalogRun>("/analytics/catalog/run", {
      method: "POST",
      body: JSON.stringify(requestFor("appointment_overview", startDate, endDate)),
    }),
    tiaRequest<AnalyticsCatalogRun>("/analytics/catalog/run", {
      method: "POST",
      body: JSON.stringify(requestFor("new_patients_trend", startDate, endDate, fullYear ? "month" : "day")),
    }),
    tiaRequest<AnalyticsCatalogRun>("/analytics/catalog/run", {
      method: "POST",
      body: JSON.stringify(requestFor("revenue_trend", startDate, endDate, fullYear ? "month" : "day")),
    }),
    tiaRequest<Profitability>(`/finance/profitability?start_date=${startDate}&end_date=${endDate}`),
  ]);

  const finance = profitability.currencies.find((item) => item.currency === "EGP") || profitability.currencies[0];
  const newPatientCount = newPatients.chart_data.series[0]?.values.reduce<number>((sum, value) => sum + (value ?? 0), 0) ?? 0;

  return (
    <section className="mb-7">
      <div className="mb-3">
        <h2 className="text-lg font-black text-slate-950">ملخص {periodLabel}</h2>
        <p className="mt-1 text-xs text-[var(--muted)]">الأرقام تخص الفترة التقويمية المختارة، وليست آخر 30 يوم.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="إجمالي المواعيد"
          value={metricNumber(appointments, "appointments")}
          detail={`${metricNumber(appointments, "completed_appointments").toLocaleString("ar-EG")} جلسة مكتملة`}
          icon={CalendarCheck2}
        />
        <StatCard
          label="المصروفات"
          value={finance ? formatMoney(finance.expenses_minor, finance.currency) : "—"}
          detail="المصروفات المسجلة بتاريخ وقوعها خلال الفترة"
          icon={ReceiptText}
        />
        <StatCard
          label="عملاء جدد"
          value={newPatientCount.toLocaleString("ar-EG")}
          detail="حسب تاريخ انضمام العميل المسجل"
          icon={ContactRound}
        />
        <StatCard
          label="الأرباح"
          value={finance ? formatMoney(finance.profit_minor, finance.currency) : "—"}
          detail={finance ? `صافي دخل ${formatMoney(finance.net_revenue_minor, finance.currency)} − مصروفات` : "لا توجد حركة مالية مسجلة"}
          icon={TrendingUp}
        />
      </div>

      <Card className="mt-5">
        <CardHeader>
          <CardTitle>تطور الدخل</CardTitle>
          <p className="mt-1 text-xs text-[var(--muted)]">يساعدك تعرف هل دخل العيادة بيتحسن أو بيتراجع داخل الفترة المختارة، وتحدد الأيام أو الشهور الأقوى والأضعف.</p>
        </CardHeader>
        <CardContent>
          <RevenueLineChart result={revenue} />
        </CardContent>
      </Card>
    </section>
  );
}
