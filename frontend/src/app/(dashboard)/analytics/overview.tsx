import { CalendarCheck2, ContactRound, Percent, WalletCards } from "lucide-react";

import { StatCard } from "@/components/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";
import { tiaRequest } from "@/lib/tia/api";

type AnalyticsMoney = {
  currency: string;
  recorded_paid_minor: number;
  outstanding_balance_minor: number;
};

type AnalyticsBreakdown = {
  id: string;
  name: string;
  appointments: number;
  completed: number;
  no_show: number;
};

type AnalyticsDaily = {
  date: string;
  appointments: number;
  completed: number;
  no_show: number;
  new_patients: number;
};

type AnalyticsOverview = {
  total_appointments: number;
  completed_appointments: number;
  no_show_appointments: number;
  cancelled_appointments: number;
  attendance_rate_percent: number;
  new_patients: number;
  conversations_started: number;
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

export async function AnalyticsOverviewPanel() {
  const overview = await tiaRequest<AnalyticsOverview>("/analytics/overview?days=30");
  const primaryMoney = overview.money[0];
  const recentDays = overview.daily.slice(-7);

  return (
    <section className="mb-7">
      <div className="mb-3">
        <h2 className="text-lg font-black text-slate-950">ملخص آخر 30 يوم</h2>
        <p className="mt-1 text-xs text-[var(--muted)]">أهم مؤشرات الحجز والحضور والعملاء والتحصيل.</p>
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
  );
}
