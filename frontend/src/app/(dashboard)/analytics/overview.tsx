import { CalendarCheck2, CircleDollarSign, ReceiptText, TrendingDown, TrendingUp } from "lucide-react";

import { StatCard } from "@/components/stat-card";
import { formatMoney } from "@/lib/format";
import { tiaRequest } from "@/lib/tia/api";
import type { AnalyticsCatalogRun, AnalyticsCatalogRunRequest } from "@/lib/types";
import { DashboardCharts } from "./dashboard-charts";

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

type FinanceTrend = {
  currency: string;
  points: Array<{
    label: string;
    start_date: string;
    end_date: string;
    net_revenue_minor: number;
  }>;
};

type PaymentBreakdown = {
  rows: Array<{ payment_method: string; currency: string; amount_minor: number; transaction_count: number }>;
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
  const granularity = fullYear ? "month" : "day";
  const trendMode = fullYear ? "year" : "month";
  const [appointments, newPatients, trend, profitability, paymentBreakdown] = await Promise.all([
    tiaRequest<AnalyticsCatalogRun>("/analytics/catalog/run", {
      method: "POST",
      body: JSON.stringify(requestFor("appointment_overview", startDate, endDate)),
    }),
    tiaRequest<AnalyticsCatalogRun>("/analytics/catalog/run", {
      method: "POST",
      body: JSON.stringify(requestFor("new_patients_trend", startDate, endDate, granularity)),
    }),
    tiaRequest<FinanceTrend>(`/finance/dashboard-trend?start_date=${startDate}&end_date=${endDate}&mode=${trendMode}`),
    tiaRequest<Profitability>(`/finance/profitability?start_date=${startDate}&end_date=${endDate}`),
    tiaRequest<PaymentBreakdown>(`/finance/payment-method-breakdown?start_date=${startDate}&end_date=${endDate}`),
  ]);

  const finance = profitability.currencies.find((item) => item.currency === "EGP") || profitability.currencies[0];
  const currency = finance?.currency || trend.currency || "EGP";
  const newPatientSeries = newPatients.chart_data.series.find((item) => item.key === "new_patients") || newPatients.chart_data.series[0];
  const newPatientCount = newPatientSeries?.values.reduce<number>((sum, value) => sum + (value ?? 0), 0) ?? 0;
  const paymentMethods = paymentBreakdown.rows.filter((row) => row.currency === currency);

  return (
    <section className="mb-7">
      <div className="mb-3">
        <h2 className="text-lg font-black text-slate-950">ملخص {periodLabel}</h2>
        <p className="mt-1 text-xs text-[var(--muted)]">الفترة كاملة من {startDate} إلى {endDate}. الأرقام المالية مبنية على المدفوعات والمرتجعات والمصروفات المسجلة فعليًا.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard label="إجمالي المقبوضات" value={finance ? formatMoney(finance.gross_payments_minor, currency) : "—"} detail="دفعات فعلية مسجلة خلال الفترة" icon={CircleDollarSign} />
        <StatCard label="المرتجعات" value={finance ? formatMoney(finance.refunds_minor, currency) : "—"} detail="مبالغ مرتجعة مسجلة خلال الفترة" icon={TrendingDown} />
        <StatCard label="صافي الدخل" value={finance ? formatMoney(finance.net_revenue_minor, currency) : "—"} detail="المقبوضات بعد خصم المرتجعات" icon={TrendingUp} />
        <StatCard label="المصروفات" value={finance ? formatMoney(finance.expenses_minor, currency) : "—"} detail="المصروفات المسجلة بتاريخ وقوعها" icon={ReceiptText} />
        <StatCard label="الربح المسجل" value={finance ? formatMoney(finance.profit_minor, currency) : "—"} detail="صافي الدخل بعد المصروفات المسجلة" icon={TrendingUp} />
        <StatCard label="إجمالي المواعيد" value={metricNumber(appointments, "appointments")} detail={`${metricNumber(appointments, "completed_appointments").toLocaleString("ar-EG")} جلسة مكتملة · ${newPatientCount.toLocaleString("ar-EG")} عميل جديد`} icon={CalendarCheck2} />
      </div>

      <div className="mt-5">
        <DashboardCharts
          fullYear={fullYear}
          startDate={startDate}
          endDate={endDate}
          revenuePoints={trend.points.map((point) => ({ label: point.label, value: point.net_revenue_minor }))}
          newPatientLabels={newPatients.chart_data.labels}
          newPatientValues={newPatientSeries?.values || []}
          paymentMethods={paymentMethods.map((row) => ({ payment_method: row.payment_method, amount_minor: row.amount_minor }))}
          appointments={{
            completed: metricNumber(appointments, "completed_appointments"),
            noShow: metricNumber(appointments, "no_show_appointments"),
            cancelled: metricNumber(appointments, "cancelled_appointments"),
          }}
          currency={currency}
        />
      </div>
    </section>
  );
}
