import type { KnowledgeHour } from "@/lib/agent-knowledge-types";

const days = [
  { weekday: 5, label: "السبت" },
  { weekday: 6, label: "الأحد" },
  { weekday: 0, label: "الإثنين" },
  { weekday: 1, label: "الثلاثاء" },
  { weekday: 2, label: "الأربعاء" },
  { weekday: 3, label: "الخميس" },
  { weekday: 4, label: "الجمعة" },
] as const;

export type WeeklyScheduleRow = {
  key: string;
  label: string;
  secondary?: string | null;
  hours: KnowledgeHour[];
};

function shortTime(value: string) {
  return value ? value.slice(0, 5) : "—";
}

function intervalsFor(hours: KnowledgeHour[], weekday: number) {
  return hours.filter((row) => row.weekday === weekday);
}

function DayCell({ hours, weekday }: { hours: KnowledgeHour[]; weekday: number }) {
  const intervals = intervalsFor(hours, weekday);
  if (!intervals.length) return <span className="text-slate-400">مغلق</span>;
  return (
    <div className="space-y-1">
      {intervals.map((row, index) => (
        <div key={`${row.weekday}-${row.start_time}-${row.end_time}-${index}`} className="whitespace-nowrap font-semibold">
          {shortTime(row.start_time)}–{shortTime(row.end_time)}
        </div>
      ))}
    </div>
  );
}

export function WeeklyScheduleTable({
  rows,
  firstHeader,
  secondHeader,
}: {
  rows: WeeklyScheduleRow[];
  firstHeader: string;
  secondHeader?: string;
}) {
  if (!rows.length) {
    return <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-[var(--muted)]">لا توجد مواعيد محفوظة.</div>;
  }

  return (
    <>
      <div className="space-y-3 md:hidden">
        {rows.map((row) => (
          <div key={row.key} className="rounded-2xl border border-[var(--border)] bg-white p-4">
            <div className="font-black text-slate-950">{row.label}</div>
            {secondHeader && row.secondary && <div className="mt-1 text-xs text-[var(--muted)]">{row.secondary}</div>}
            <div className="mt-4 grid grid-cols-2 gap-2">
              {days.map((day) => {
                const intervals = intervalsFor(row.hours, day.weekday);
                return (
                  <div key={day.weekday} className="rounded-xl bg-slate-50 p-3 text-xs">
                    <div className="font-bold text-slate-700">{day.label}</div>
                    <div className="mt-1.5 text-[var(--muted)]">
                      {intervals.length
                        ? intervals.map((item, index) => <div key={`${item.start_time}-${index}`} className="font-semibold text-slate-900">{shortTime(item.start_time)}–{shortTime(item.end_time)}</div>)
                        : "مغلق"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="hidden overflow-x-auto rounded-2xl border border-[var(--border)] bg-white md:block">
        <table className="w-full min-w-[1050px] text-right text-xs">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="whitespace-nowrap px-3 py-3 font-black">{firstHeader}</th>
              {secondHeader && <th className="whitespace-nowrap px-3 py-3 font-black">{secondHeader}</th>}
              {days.map((day) => <th key={day.weekday} className="whitespace-nowrap px-3 py-3 text-center font-black">{day.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-t border-slate-100 transition hover:bg-slate-50/70">
                <td className="whitespace-nowrap px-3 py-3 font-bold">{row.label}</td>
                {secondHeader && <td className="whitespace-nowrap px-3 py-3">{row.secondary || "—"}</td>}
                {days.map((day) => <td key={day.weekday} className="px-3 py-3 text-center align-top"><DayCell hours={row.hours} weekday={day.weekday} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
