"use client";

import Link from "next/link";
import { useActionState, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  BookmarkPlus,
  Download,
  Filter,
  LoaderCircle,
  Play,
  Rows3,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatMoney } from "@/lib/format";
import type {
  AnalyticsBIMetric,
  AnalyticsCatalog,
  AnalyticsCatalogCategory,
  AnalyticsCatalogChart,
  AnalyticsCatalogChartSeries,
  AnalyticsCatalogDefinition,
  AnalyticsCatalogRun,
  AnalyticsSavedView,
  AnalyticsSavedViewDisplayMode,
} from "@/lib/types";
import { AnalyticsAudienceActions } from "./audience-actions";
import {
  deleteAnalyticsViewAction,
  runAnalyticsCatalogAction,
  saveAnalyticsViewAction,
  type AnalyticsCatalogState,
  type AnalyticsSavedViewState,
} from "./actions";

const categoryLabels: Record<AnalyticsCatalogCategory, string> = {
  revenue: "الإيرادات",
  patients: "العملاء",
  appointments: "المواعيد",
  services: "الخدمات",
  doctors: "الدكاترة",
  branches: "الفروع",
  retention: "الاحتفاظ بالعملاء",
  funnels: "رحلة العميل",
};

type AnalyticsCategoryGroup = "performance" | "customers" | "services" | "team";

const categoryGroups: Array<{ key: AnalyticsCategoryGroup; label: string; description: string; categories: AnalyticsCatalogCategory[] }> = [
  { key: "performance", label: "الأداء", description: "الإيرادات والمواعيد", categories: ["revenue", "appointments"] },
  { key: "customers", label: "العملاء", description: "النشاط والعودة والفرص", categories: ["patients", "retention", "funnels"] },
  { key: "services", label: "الخدمات", description: "أداء الخدمات والطلب عليها", categories: ["services"] },
  { key: "team", label: "الفريق والفروع", description: "الدكاترة والفروع", categories: ["doctors", "branches"] },
];

const chartLabels: Record<AnalyticsCatalogChart, string> = {
  kpi: "بطاقات",
  line: "خط",
  bar: "أعمدة",
  heatmap: "خريطة حرارية",
  funnel: "مسار",
  table: "جدول",
};

const quickAccessKeys = [
  "revenue_overview",
  "appointment_overview",
  "revenue_by_service",
  "revenue_by_doctor",
  "lapsed_patients",
] as const;

const initialState: AnalyticsCatalogState = { result: null, error: null };
const initialSavedViewState: AnalyticsSavedViewState = { view: null, error: null };

type DisplayMode = "visual" | "table" | "both";

function metricValue(metric: AnalyticsBIMetric) {
  if (metric.currency && typeof metric.value === "number") return formatMoney(metric.value, metric.currency);
  if (typeof metric.value === "number" && (metric.key.includes("rate") || metric.key.includes("percent") || metric.key.includes("change_percent"))) {
    return `${metric.value.toLocaleString("ar-EG", { maximumFractionDigits: 1 })}%`;
  }
  if (typeof metric.value === "number") return metric.value.toLocaleString("ar-EG", { maximumFractionDigits: 1 });
  return metric.value;
}

function seriesValue(series: AnalyticsCatalogChartSeries, value: number | null) {
  if (value === null) return "—";
  if (series.format === "money") return formatMoney(value, series.currency || "EGP");
  if (series.format === "percent") return `${value.toLocaleString("ar-EG", { maximumFractionDigits: 1 })}%`;
  return value.toLocaleString("ar-EG", { maximumFractionDigits: 1 });
}

function defaultPeriodLabel(days: number | null) {
  if (!days) return "كل التاريخ";
  if (days === 30) return "30 يوم";
  if (days === 90) return "90 يوم";
  if (days === 180) return "6 شهور";
  if (days === 365) return "سنة";
  if (days === 730) return "سنتين";
  return `${days} يوم`;
}

function isComparisonMetric(key: string) {
  return key.endsWith("_previous") || key.endsWith("_change_percent") || key.endsWith("_delta_points");
}

function comparisonDelta(metrics: AnalyticsBIMetric[], key: string) {
  return metrics.find(item => item.key === `${key}_change_percent`)
    || metrics.find(item => item.key === `${key}_delta_points`);
}

function deltaValue(metric: AnalyticsBIMetric) {
  if (metric.value === "—") return "—";
  if (typeof metric.value !== "number") return String(metric.value);
  const prefix = metric.value > 0 ? "+" : "";
  if (metric.key.endsWith("_delta_points")) return `${prefix}${metric.value.toLocaleString("ar-EG", { maximumFractionDigits: 1 })} نقطة`;
  return `${prefix}${metric.value.toLocaleString("ar-EG", { maximumFractionDigits: 1 })}%`;
}

function MetricCards({ metrics }: { metrics: AnalyticsBIMetric[] }) {
  const currentMetrics = metrics.filter(metric => !isComparisonMetric(metric.key));
  if (!currentMetrics.length) return null;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {currentMetrics.map(metric => {
        const previous = metrics.find(item => item.key === `${metric.key}_previous`);
        const delta = comparisonDelta(metrics, metric.key);
        return (
          <div key={metric.key} className="rounded-2xl border border-[var(--border)] bg-slate-50 p-4">
            <div className="text-xs text-[var(--muted)]">{metric.label}</div>
            <div className="mt-2 text-2xl font-black">{metricValue(metric)}</div>
            {(previous || delta) && (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                {delta && (
                  <span className="rounded-full bg-slate-100 px-2 py-1 font-black text-slate-700">
                    {deltaValue(delta)}
                  </span>
                )}
                {previous && <span className="text-[var(--muted)]">الفترة السابقة: {metricValue(previous)}</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function BarVisualization({ result, series }: { result: AnalyticsCatalogRun; series: AnalyticsCatalogChartSeries }) {
  const values = series.values.map(value => value ?? 0);
  const max = Math.max(1, ...values.map(value => Math.abs(value)));
  const visibleLabels = result.chart_data.labels.slice(0, 15);
  return (
    <div className="space-y-3">
      <div className="text-xs font-bold text-[var(--muted)]">{series.label}</div>
      {visibleLabels.map((label, index) => {
        const value = values[index] || 0;
        const width = value === 0 ? 0 : Math.max(2, Math.abs(value) / max * 100);
        return (
          <div key={`${label}-${index}`} className="grid grid-cols-[minmax(100px,180px)_1fr_auto] items-center gap-3 text-xs">
            <span className="truncate font-bold" title={label}>{label}</span>
            <div className="h-3 overflow-hidden rounded-full bg-slate-100">
              <div className={`h-full rounded-full ${value < 0 ? "bg-rose-500" : "bg-teal-700"}`} style={{ width: `${width}%` }} />
            </div>
            <span className="min-w-20 text-left font-black">{seriesValue(series, series.values[index] ?? null)}</span>
          </div>
        );
      })}
      {result.chart_data.labels.length > visibleLabels.length && (
        <div className="text-[11px] text-[var(--muted)]">الرسم يعرض أول {visibleLabels.length.toLocaleString("ar-EG")} عناصر؛ الجدول يحتوي على كل النتائج المعروضة.</div>
      )}
    </div>
  );
}

function LineVisualization({ result, series }: { result: AnalyticsCatalogRun; series: AnalyticsCatalogChartSeries }) {
  if (!series.values.length) return null;
  const values = series.values.map(value => value ?? 0);
  const width = 720;
  const height = 230;
  const padding = 24;
  const min = Math.min(0, ...values);
  const max = Math.max(1, ...values);
  const span = Math.max(1, max - min);
  const coordinates = values.map((value, index) => ({
    x: values.length === 1 ? width / 2 : padding + index * ((width - padding * 2) / (values.length - 1)),
    y: height - padding - ((value - min) / span) * (height - padding * 2),
  }));
  const points = coordinates.map(point => `${point.x},${point.y}`).join(" ");
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3 text-xs font-bold text-[var(--muted)]">
        <span>{series.label}</span>
        <span>أعلى قيمة: {seriesValue(series, Math.max(...values))}</span>
      </div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-56 min-w-[620px] w-full" role="img" aria-label={`${result.title} chart`}>
          <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} className="stroke-slate-200" />
          <polyline points={points} fill="none" className="stroke-teal-700" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
          {coordinates.map((point, index) => (
            <circle key={index} cx={point.x} cy={point.y} r="4" className="fill-white stroke-teal-700" strokeWidth="3">
              <title>{`${result.chart_data.labels[index] || ""}: ${seriesValue(series, series.values[index] ?? null)}`}</title>
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

function HeatmapVisualization({ result }: { result: AnalyticsCatalogRun }) {
  if (!result.chart_data.labels.length || !result.chart_data.series.length) return null;
  const numericValues = result.chart_data.series.flatMap(series => series.values.map(value => value ?? 0));
  const max = Math.max(1, ...numericValues.map(value => Math.abs(value)));

  function cellClass(value: number) {
    if (value <= 0) return "bg-slate-50 text-slate-400";
    const ratio = Math.abs(value) / max;
    if (ratio >= 0.8) return "bg-teal-700 text-white";
    if (ratio >= 0.6) return "bg-teal-500 text-white";
    if (ratio >= 0.4) return "bg-teal-300 text-teal-950";
    if (ratio >= 0.2) return "bg-teal-200 text-teal-950";
    return "bg-teal-100 text-teal-900";
  }

  return (
    <div className="overflow-x-auto">
      <div className="min-w-max">
        <div className="grid gap-1" style={{ gridTemplateColumns: `90px repeat(${result.chart_data.labels.length}, minmax(54px, 1fr))` }}>
          <div />
          {result.chart_data.labels.map(label => <div key={label} className="px-1 py-2 text-center text-[10px] font-bold text-[var(--muted)]">{label}</div>)}
          {result.chart_data.series.map(series => (
            <div key={series.key} className="contents">
              <div className="flex items-center px-2 text-xs font-black">{series.label}</div>
              {series.values.map((raw, index) => {
                const value = raw ?? 0;
                return (
                  <div
                    key={`${series.key}-${result.chart_data.labels[index] || index}`}
                    className={`rounded-lg px-1 py-3 text-center text-[10px] font-black ${cellClass(value)}`}
                    title={`${series.label} · ${result.chart_data.labels[index] || ""}: ${seriesValue(series, raw ?? null)}`}
                  >
                    {seriesValue(series, raw ?? null)}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FunnelVisualization({ result }: { result: AnalyticsCatalogRun }) {
  const series = result.chart_data.series[0];
  if (!series) return null;
  const values = series.values.map(value => value ?? 0);
  const first = Math.max(0, values[0] || 0);
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {result.chart_data.labels.map((label, index) => {
        const value = values[index] || 0;
        const fromStart = first > 0 ? Math.max(0, Math.min(100, value / first * 100)) : 0;
        const previous = index > 0 ? values[index - 1] || 0 : first;
        const fromPrevious = index > 0 && previous > 0 ? Math.max(0, Math.min(100, value / previous * 100)) : 100;
        return (
          <div key={`${label}-${index}`} className="rounded-2xl border border-[var(--border)] bg-slate-50 p-4">
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="text-xs text-[var(--muted)]">{label}</div>
                <div className="mt-1 text-xl font-black">{seriesValue(series, series.values[index] ?? null)}</div>
              </div>
              {index > 0 && (
                <div className="text-left text-[11px] leading-5 text-[var(--muted)]">
                  <div><span className="font-black text-slate-800">{fromPrevious.toLocaleString("ar-EG", { maximumFractionDigits: 1 })}%</span> من المرحلة السابقة</div>
                  <div>{fromStart.toLocaleString("ar-EG", { maximumFractionDigits: 1 })}% من بداية المسار</div>
                </div>
              )}
            </div>
            <div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-teal-700" style={{ width: `${fromStart}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BreakdownLeader({ result }: { result: AnalyticsCatalogRun }) {
  const series = result.chart_data.series[0];
  if (!series || !result.chart_data.labels.length || series.values[0] === null || series.values[0] === undefined) return null;
  return (
    <div className="rounded-2xl border border-teal-100 bg-teal-50/50 p-4">
      <div className="text-[11px] font-bold text-teal-800">الأعلى في {series.label}</div>
      <div className="mt-1 flex flex-wrap items-end justify-between gap-2">
        <div className="text-lg font-black text-teal-950">{result.chart_data.labels[0]}</div>
        <div className="text-xl font-black text-teal-950">{seriesValue(series, series.values[0])}</div>
      </div>
    </div>
  );
}

function ResultTable({ result }: { result: AnalyticsCatalogRun }) {
  const metricKeys = Array.from(new Map(result.rows.flatMap(row => row.metrics.map(metric => [metric.key, metric]))).values());
  return (
    <div className="overflow-x-auto rounded-2xl border border-[var(--border)]">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-slate-50 text-right text-xs text-[var(--muted)]">
          <tr><th className="p-3">الاسم</th>{metricKeys.map(metric => <th key={metric.key} className="p-3">{metric.label}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {result.rows.map((row, index) => (
            <tr key={`${row.key || row.label}-${index}`}>
              <td className="p-3 font-bold">
                {result.result_kind === "patient_list" && row.key
                  ? <Link href={`/patients/${row.key}`} className="text-teal-800 hover:underline">{row.label}</Link>
                  : row.label}
                {row.secondary_label && <div className="mt-0.5 text-[11px] font-normal text-[var(--muted)]">{row.secondary_label}</div>}
              </td>
              {metricKeys.map(column => {
                const metric = row.metrics.find(item => item.key === column.key);
                return <td key={column.key} className="p-3">{metric ? metricValue(metric) : "—"}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function downloadCsv(result: AnalyticsCatalogRun) {
  const response = await fetch("/api/analytics/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(result.request),
  });
  if (!response.ok) {
    let message = "حصل خطأ أثناء تجهيز ملف CSV.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {}
    throw new Error(message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || `tia-${result.analysis_key}.csv`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function hasFilter(definition: AnalyticsCatalogDefinition, key: AnalyticsCatalogDefinition["filters"][number]) {
  return definition.filters.includes(key);
}

function resultCountLabel(result: AnalyticsCatalogRun) {
  if (result.result_kind === "patient_list") return "عميل";
  if (result.result_kind === "trend") return "فترة";
  if (result.result_kind === "breakdown") return "عنصر";
  return "نتيجة";
}

function SaveViewControl({ result, chart, displayMode }: { result: AnalyticsCatalogRun; chart: AnalyticsCatalogChart; displayMode: AnalyticsSavedViewDisplayMode }) {
  const [state, action, pending] = useActionState<AnalyticsSavedViewState, FormData>(saveAnalyticsViewAction, initialSavedViewState);
  const suggestedName = `${result.title} — ${result.period_label}`.slice(0, 160);
  return (
    <details className="relative">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-xs font-bold">
        <BookmarkPlus size={16} /> حفظ العرض
      </summary>
      <form action={action} className="absolute left-0 z-20 mt-2 w-72 rounded-2xl border border-[var(--border)] bg-white p-3 shadow-xl">
        <input type="hidden" name="request" value={JSON.stringify(result.request)} />
        <input type="hidden" name="chart" value={chart} />
        <input type="hidden" name="display_mode" value={displayMode} />
        <label className="text-xs font-black">اسم العرض
          <input name="name" defaultValue={suggestedName} maxLength={160} className="form-control mt-1" />
        </label>
        <p className="mt-2 text-[11px] leading-5 text-[var(--muted)]">هنحفظ التحليل والفلاتر وطريقة العرض فقط. الأرقام نفسها تتحدث كل مرة تفتحه.</p>
        <Button type="submit" className="mt-3 w-full" disabled={pending}>{pending ? <LoaderCircle size={15} className="animate-spin" /> : <BookmarkPlus size={15} />} حفظ</Button>
        {state.view && <div className="mt-2 text-[11px] font-bold text-emerald-700">اتحفظ باسم «{state.view.name}».</div>}
        {state.error && <div className="mt-2 text-[11px] font-bold text-red-700">{state.error}</div>}
      </form>
    </details>
  );
}

function ResultPanel({ result, initialChart, initialDisplayMode }: { result: AnalyticsCatalogRun; initialChart?: AnalyticsCatalogChart | null; initialDisplayMode?: AnalyticsSavedViewDisplayMode | null }) {
  const defaultMode: DisplayMode = result.result_kind === "patient_list" ? "table" : "visual";
  const [displayMode, setDisplayMode] = useState<DisplayMode>(initialDisplayMode || defaultMode);
  const visualCharts = result.supported_charts.filter(chart => chart !== "table");
  const preferredChart = initialChart && result.supported_charts.includes(initialChart) ? initialChart : result.chart;
  const [chartType, setChartType] = useState<AnalyticsCatalogChart>(preferredChart);
  const [exportPending, setExportPending] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [seriesKey, setSeriesKey] = useState(result.chart_data.series[0]?.key || "");
  const activeSeries = result.chart_data.series.find(series => series.key === seriesKey) || result.chart_data.series[0];
  const hasVisual = visualCharts.length > 0 && (chartType === "kpi" || chartType === "funnel" || Boolean(activeSeries));
  const showVisual = hasVisual && (displayMode === "visual" || displayMode === "both");
  const showTable = displayMode === "table" || displayMode === "both" || !hasVisual;
  const visualLabel = chartType === "kpi" ? "البطاقات" : "الرسم";

  if (!result.rows.length) {
    return (
      <div className="mt-6 border-t border-[var(--border)] pt-5">
        <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
          <div className="font-black">مفيش بيانات مطابقة للشروط دي</div>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{result.answer}</p>
          <p className="mt-1 text-xs text-slate-500">غيّر الفترة أو الفلاتر لو محتاج؛ Tia لا توسّع الشروط من نفسها.</p>
          {result.definitions.length > 0 && (
            <details className="mx-auto mt-4 max-w-2xl rounded-xl border border-[var(--border)] bg-white p-3 text-right text-xs leading-6 text-slate-700">
              <summary className="cursor-pointer font-black">ليه النتيجة طلعت كده؟</summary>
              <ul className="mt-2 list-disc space-y-1 pr-5">{result.definitions.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </details>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-4 border-t border-[var(--border)] pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2"><Rows3 size={18} /><h3 className="text-lg font-black">{result.title}</h3></div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {result.period_label}{result.result_kind !== "summary" && <> · {result.rows.length.toLocaleString("ar-EG")} {resultCountLabel(result)}</>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {hasVisual && result.supported_charts.includes("table") && (
            <div className="flex rounded-xl border border-[var(--border)] bg-white p-1">
              {(["visual", "table", "both"] as DisplayMode[]).map(mode => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setDisplayMode(mode)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold ${displayMode === mode ? "bg-slate-900 text-white" : "text-slate-600"}`}
                >
                  {mode === "visual" ? visualLabel : mode === "table" ? "الجدول" : "الاتنين"}
                </button>
              ))}
            </div>
          )}
          <SaveViewControl result={result} chart={chartType} displayMode={displayMode} />
          {result.allowed_actions.includes("export") && <Button type="button" variant="outline" disabled={exportPending} onClick={async () => {
            setExportPending(true); setExportError(null);
            try { await downloadCsv(result); } catch (error) { setExportError(error instanceof Error ? error.message : "حصل خطأ أثناء التصدير."); }
            finally { setExportPending(false); }
          }}>{exportPending ? <LoaderCircle size={16} className="animate-spin" /> : <Download size={16} />} تصدير CSV</Button>}
        </div>
      </div>
      {exportError && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700">{exportError}</div>}

      {result.highlights.length > 0 && result.result_kind !== "summary" && <MetricCards metrics={result.highlights} />}
      {result.result_kind === "breakdown" && result.highlights.length === 0 && result.chart !== "heatmap" && <BreakdownLeader result={result} />}

      {showVisual && (
        <div className="rounded-2xl border border-[var(--border)] p-4">
          {(visualCharts.length > 1 || (result.chart_data.series.length > 1 && ["bar", "line"].includes(chartType))) && (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
              <div className="flex flex-wrap gap-2">
                {visualCharts.length > 1 && visualCharts.map(chart => (
                  <button key={chart} type="button" onClick={() => setChartType(chart)} className={`rounded-lg px-3 py-1.5 text-xs font-bold ${chartType === chart ? "bg-teal-50 text-teal-800" : "bg-slate-50 text-slate-600"}`}>
                    {chartLabels[chart]}
                  </button>
                ))}
              </div>
              {result.chart_data.series.length > 1 && ["bar", "line"].includes(chartType) && (
                <select value={activeSeries?.key || ""} onChange={event => setSeriesKey(event.target.value)} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs font-bold">
                  {result.chart_data.series.map(series => <option key={series.key} value={series.key}>{series.label}</option>)}
                </select>
              )}
            </div>
          )}
          {chartType === "kpi" && <MetricCards metrics={result.rows[0]?.metrics || []} />}
          {chartType === "bar" && activeSeries && <BarVisualization result={result} series={activeSeries} />}
          {chartType === "line" && activeSeries && <LineVisualization result={result} series={activeSeries} />}
          {chartType === "heatmap" && <HeatmapVisualization result={result} />}
          {chartType === "funnel" && <FunnelVisualization result={result} />}
        </div>
      )}

      {showTable && <ResultTable result={result} />}

      {result.result_kind === "patient_list" && result.audience_plan && (
        <AnalyticsAudienceActions
          key={result.analysis_key}
          result={{ question: result.title, mode: "audience", audience_plan: result.audience_plan, rows: result.rows }}
          allowedActions={result.allowed_actions}
        />
      )}

      {result.definitions.length > 0 && (
        <details className="rounded-xl border border-[var(--border)] bg-slate-50 p-3 text-xs leading-6 text-slate-700">
          <summary className="cursor-pointer font-black">تعريف وطريقة الحساب</summary>
          <ul className="mt-2 list-disc space-y-1 pr-5">{result.definitions.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

export function AnalyticsCatalogPanel({ catalog, savedViews }: { catalog: AnalyticsCatalog; savedViews: AnalyticsSavedView[] }) {
  const groups = useMemo(() => categoryGroups.filter(group => group.categories.some(category => catalog.analyses.some(analysis => analysis.category === category))), [catalog.analyses]);
  const [groupKey, setGroupKey] = useState<AnalyticsCategoryGroup>(groups[0]?.key || "performance");
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState(catalog.analyses[0]?.key || "");
  const [preset, setPreset] = useState<AnalyticsSavedView | null>(null);
  const [dirty, setDirty] = useState(true);
  const [state, action, pending] = useActionState<AnalyticsCatalogState, FormData>(runAnalyticsCatalogAction, initialState);
  const resultRef = useRef<HTMLDivElement>(null);

  const normalizedQuery = query.trim().toLocaleLowerCase("ar");
  const visibleAnalyses = useMemo(() => catalog.analyses.filter(item => {
    if (normalizedQuery) {
      return `${item.title} ${item.description} ${categoryLabels[item.category]}`.toLocaleLowerCase("ar").includes(normalizedQuery);
    }
    const activeGroup = groups.find(group => group.key === groupKey) || groups[0];
    return Boolean(activeGroup?.categories.includes(item.category));
  }), [catalog.analyses, groupKey, groups, normalizedQuery]);

  const selected = visibleAnalyses.find(item => item.key === selectedKey) || visibleAnalyses[0];
  const presetRequest = preset && selected && preset.analysis_key === selected.key ? preset.request : null;
  const result = selected && !dirty && !pending && state.result?.analysis_key === selected.key ? state.result : null;
  const quickAccess = quickAccessKeys.map(key => catalog.analyses.find(item => item.key === key)).filter((item): item is AnalyticsCatalogDefinition => Boolean(item));

  useEffect(() => {
    if (result) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [result]);

  function chooseGroup(next: AnalyticsCategoryGroup) {
    setGroupKey(next);
    setQuery("");
    setPreset(null);
    setDirty(true);
    const group = groups.find(item => item.key === next);
    const first = group ? catalog.analyses.find(item => group.categories.includes(item.category)) : null;
    if (first) setSelectedKey(first.key);
  }

  function chooseAnalysis(item: AnalyticsCatalogDefinition) {
    setSelectedKey(item.key);
    const group = groups.find(candidate => candidate.categories.includes(item.category));
    if (group) setGroupKey(group.key);
    setPreset(null);
    setDirty(true);
  }

  function chooseSavedView(view: AnalyticsSavedView) {
    const definition = catalog.analyses.find(item => item.key === view.analysis_key);
    if (!definition) return;
    setQuery("");
    const group = groups.find(candidate => candidate.categories.includes(definition.category));
    if (group) setGroupKey(group.key);
    setSelectedKey(definition.key);
    setPreset(view);
    setDirty(true);
  }

  if (!catalog.analyses.length) {
    return <div className="rounded-2xl border border-[var(--border)] p-6 text-sm text-[var(--muted)]">مفيش تحليلات مسجلة.</div>;
  }

  const hasEntityFilters = selected && (["service", "branch", "doctor"] as const).some(key => hasFilter(selected, key));
  const hasExtraFilters = selected && (["granularity", "limit", "marketing_consent", "comparison"] as const).some(key => hasFilter(selected, key));
  const periodDefault = presetRequest?.all_history ? "all" : String(presetRequest?.lookback_days ?? selected?.default_lookback_days ?? "all");
  const entityPreset = {
    service: presetRequest?.service_ids[0] || "",
    branch: presetRequest?.branch_ids[0] || "",
    doctor: presetRequest?.doctor_ids[0] || "",
  };
  const formKey = `${selected?.key || "none"}-${preset?.id || "fresh"}`;

  return (
    <section className="mb-6 rounded-3xl border border-[var(--border)] bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-teal-700 text-white"><BarChart3 size={21} /></span>
          <div>
            <h2 className="text-lg font-black">التقارير</h2>
            <p className="mt-1 text-sm leading-6 text-slate-600">اختر التقرير المناسب، وحدد الفترة فقط. الخيارات الإضافية موجودة عند الحاجة.</p>
          </div>
        </div>
        <label className="relative w-full max-w-sm">
          <Search size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="ابحث عن تقرير" className="form-control pr-9" />
        </label>
      </div>

      {savedViews.length > 0 && (
        <details className="mt-5 rounded-2xl border border-[var(--border)] bg-slate-50 p-3">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-black"><BookmarkPlus size={15} /> التقارير المحفوظة <span className="font-normal text-[var(--muted)]">({savedViews.length})</span></summary>
          <p className="mt-2 text-[11px] leading-5 text-[var(--muted)]">افتح أي تقرير محفوظ لإعادة تشغيله بأحدث بيانات العيادة.</p>
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {savedViews.map(view => {
              const definition = catalog.analyses.find(item => item.key === view.analysis_key);
              return (
                <div key={view.id} className={`flex items-center gap-2 rounded-xl border bg-white p-2 ${preset?.id === view.id ? "border-teal-400" : "border-[var(--border)]"}`}>
                  <button type="button" onClick={() => chooseSavedView(view)} className="min-w-0 flex-1 text-right">
                    <div className="truncate text-xs font-black">{view.name}</div>
                    <div className="mt-0.5 truncate text-[10px] text-[var(--muted)]">{definition?.title || "تقرير محفوظ"}</div>
                  </button>
                  <form action={deleteAnalyticsViewAction}>
                    <input type="hidden" name="view_id" value={view.id} />
                    <button type="submit" title="حذف التقرير المحفوظ" className="grid size-8 place-items-center rounded-lg text-slate-400 transition hover:bg-red-50 hover:text-red-600"><Trash2 size={14} /></button>
                  </form>
                </div>
              );
            })}
          </div>
        </details>
      )}

      {!normalizedQuery && quickAccess.length > 0 && (
        <div className="mt-5 rounded-2xl border border-teal-100 bg-teal-50/40 p-3">
          <div className="flex items-center gap-2 text-xs font-black text-teal-900"><Sparkles size={15} /> تقارير شائعة</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {quickAccess.map(item => (
              <button key={item.key} type="button" onClick={() => chooseAnalysis(item)} className="rounded-xl border border-teal-200 bg-white px-3 py-2 text-xs font-bold text-teal-900 transition hover:border-teal-400">
                {item.title}
              </button>
            ))}
          </div>
        </div>
      )}

      {normalizedQuery ? (
        <div className="mt-5 text-xs font-bold text-[var(--muted)]">نتائج البحث من كل أقسام التقارير.</div>
      ) : (
        <div className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {groups.map(group => {
            const count = catalog.analyses.filter(analysis => group.categories.includes(analysis.category)).length;
            const active = groupKey === group.key;
            return (
              <button key={group.key} type="button" onClick={() => chooseGroup(group.key)} className={`rounded-2xl border p-3 text-right transition ${active ? "border-teal-600 bg-teal-50" : "border-[var(--border)] bg-white hover:border-teal-200"}`}>
                <div className={`text-sm font-black ${active ? "text-teal-900" : ""}`}>{group.label}</div>
                <div className="mt-1 text-[11px] text-[var(--muted)]">{group.description} · {count.toLocaleString("ar-EG")} تقارير</div>
              </button>
            );
          })}
        </div>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-[.85fr_1.15fr]">
        <div className="grid content-start gap-2">
          {visibleAnalyses.map(item => (
            <button key={item.key} type="button" onClick={() => chooseAnalysis(item)} className={`rounded-2xl border p-4 text-right transition ${selected?.key === item.key ? "border-teal-500 bg-teal-50/60" : "border-[var(--border)] hover:border-teal-200"}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-black">{item.title}</div>
                  <div className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--muted)]">{item.description}</div>
                </div>
                {normalizedQuery && <span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-600">{categoryLabels[item.category]}</span>}
              </div>
            </button>
          ))}
          {!visibleAnalyses.length && <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-[var(--muted)]">لا يوجد تقرير مطابق للبحث.</div>}
        </div>

        {selected && (
          <form key={formKey} action={action} onSubmit={() => setDirty(false)} className="h-fit rounded-2xl border border-[var(--border)] bg-slate-50 p-4">
            <input type="hidden" name="analysis_key" value={selected.key} />
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <Filter size={17} className="mt-0.5" />
                <div>
                  <div className="font-black">{selected.title}</div>
                  {preset && <div className="mt-1 text-[10px] font-bold text-indigo-700">بدأت من العرض المحفوظ: {preset.name}</div>}
                  <div className="mt-1 text-xs leading-5 text-[var(--muted)]">{selected.description}</div>
                </div>
              </div>
              {selected.default_lookback_days !== null && <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-bold text-slate-500">الافتراضي: {defaultPeriodLabel(selected.default_lookback_days)}</span>}
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {hasFilter(selected, "period") && (
                <label className="text-xs font-bold">الفترة
                  <select name="period" defaultValue={periodDefault} className="form-control mt-1">
                    <option value="7">آخر 7 أيام</option><option value="30">آخر 30 يوم</option><option value="90">آخر 90 يوم</option><option value="180">آخر 6 شهور</option><option value="365">آخر سنة</option><option value="730">آخر سنتين</option><option value="all">كل التاريخ</option>
                  </select>
                </label>
              )}
              {hasFilter(selected, "inactivity_days") && (
                <label className="text-xs font-bold">منقطع من
                  <select name="inactivity_days" defaultValue={String(presetRequest?.inactivity_days ?? selected.default_inactivity_days ?? 180)} className="form-control mt-1">
                    <option value="30">30 يوم</option><option value="60">60 يوم</option><option value="90">90 يوم</option><option value="120">120 يوم</option><option value="180">6 شهور</option><option value="365">سنة</option>
                  </select>
                </label>
              )}
              {hasFilter(selected, "min_visits") && <label className="text-xs font-bold">أقل عدد زيارات<input name="min_visits" type="number" min={1} max={100} defaultValue={presetRequest?.min_visits ?? selected.default_min_visits ?? undefined} className="form-control mt-1" /></label>}
              {hasFilter(selected, "max_visits") && <label className="text-xs font-bold">أقصى عدد زيارات<input name="max_visits" type="number" min={1} max={100} defaultValue={presetRequest?.max_visits ?? selected.default_max_visits ?? undefined} className="form-control mt-1" /></label>}
            </div>

            {hasEntityFilters && (
              <details open={Boolean(entityPreset.service || entityPreset.branch || entityPreset.doctor) || undefined} className="mt-4 rounded-xl border border-[var(--border)] bg-white p-3">
                <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-black"><Filter size={15} /> فلترة أدق <span className="font-normal text-[var(--muted)]">(اختياري)</span></summary>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {hasFilter(selected, "service") && (
                    <label className="text-xs font-bold">الخدمة
                      <select name="service_id" defaultValue={entityPreset.service} className="form-control mt-1"><option value="">كل الخدمات</option>{catalog.services.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
                    </label>
                  )}
                  {hasFilter(selected, "branch") && (
                    <label className="text-xs font-bold">الفرع
                      <select name="branch_id" defaultValue={entityPreset.branch} className="form-control mt-1"><option value="">كل الفروع</option>{catalog.branches.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
                    </label>
                  )}
                  {hasFilter(selected, "doctor") && (
                    <label className="text-xs font-bold">الدكتور
                      <select name="doctor_id" defaultValue={entityPreset.doctor} className="form-control mt-1"><option value="">كل الدكاترة</option>{catalog.doctors.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
                    </label>
                  )}
                </div>
              </details>
            )}

            {hasExtraFilters && (
              <details open={Boolean(presetRequest?.comparison || presetRequest?.granularity || presetRequest?.limit || presetRequest?.marketing_consent !== null && presetRequest?.marketing_consent !== undefined) || undefined} className="mt-3 rounded-xl border border-[var(--border)] bg-white p-3">
                <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-black"><SlidersHorizontal size={15} /> خيارات العرض والحساب</summary>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {hasFilter(selected, "granularity") && <label className="text-xs font-bold">تجميع الفترة<select name="granularity" defaultValue={presetRequest?.granularity || selected.default_granularity || "month"} className="form-control mt-1"><option value="day">يومي</option><option value="week">أسبوعي</option><option value="month">شهري</option></select></label>}
                  {hasFilter(selected, "limit") && <label className="text-xs font-bold">عدد النتائج<select name="limit" defaultValue={String(presetRequest?.limit ?? selected.default_limit)} className="form-control mt-1"><option value="5">5</option><option value="10">10</option><option value="15">15</option><option value="25">25</option></select></label>}
                  {hasFilter(selected, "marketing_consent") && <label className="text-xs font-bold">موافقة الرسائل التسويقية<select name="marketing_consent" defaultValue={presetRequest?.marketing_consent === true ? "true" : presetRequest?.marketing_consent === false ? "false" : ""} className="form-control mt-1"><option value="">الكل</option><option value="true">موافق</option><option value="false">غير موافق</option></select></label>}
                </div>
                {hasFilter(selected, "comparison") && <label className="mt-3 flex items-center gap-2 text-xs font-bold"><input type="checkbox" name="comparison" defaultChecked={presetRequest?.comparison || false} /> مقارنة بالفترة السابقة بنفس الطول</label>}
              </details>
            )}

            <Button type="submit" disabled={pending} className="mt-4 w-full">{pending ? <LoaderCircle size={17} className="animate-spin" /> : <Play size={17} />} عرض التقرير</Button>
          </form>
        )}
      </div>

      <div ref={resultRef}>{result && <ResultPanel key={`${result.analysis_key}-${result.period_label}-${preset?.id || "fresh"}`} result={result} initialChart={preset?.chart} initialDisplayMode={preset?.display_mode} />}</div>
      {state.error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{state.error}{state.result && <span className="block text-xs">النتيجة المعروضة تخص آخر تشغيل ناجح.</span>}</div>}
    </section>
  );
}
