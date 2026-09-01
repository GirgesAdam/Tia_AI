const days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"];

type HourRow = { weekday: number; start_time: string; end_time: string };

export function SetupHoursFields({
  defaultStart = "10:00",
  defaultEnd = "22:00",
  hours,
}: {
  defaultStart?: string;
  defaultEnd?: string;
  hours?: HourRow[];
}) {
  return (
    <div className="space-y-2">
      {days.map((day, index) => {
        const saved = hours?.find((row) => row.weekday === index);
        const hasSavedSet = Array.isArray(hours);
        return (
          <div key={day} className="grid gap-2 rounded-xl border border-slate-100 bg-slate-50 p-3 sm:grid-cols-[110px_1fr_1fr] sm:items-center">
            <label className="flex items-center gap-2 text-xs font-bold text-slate-800">
              <input
                type="checkbox"
                name={`day_${index}`}
                defaultChecked={hasSavedSet ? Boolean(saved) : index !== 4}
                className="size-4 accent-teal-700"
              />
              {day}
            </label>
            <label className="grid grid-cols-[36px_1fr] items-center gap-2 text-[11px] font-semibold text-[var(--muted)] sm:block">
              <span className="sm:hidden">من</span>
              <input type="time" name={`start_${index}`} defaultValue={(saved?.start_time || defaultStart).slice(0, 5)} className="form-control h-9 min-h-9 py-1 text-xs" aria-label={`بداية ${day}`} />
            </label>
            <label className="grid grid-cols-[36px_1fr] items-center gap-2 text-[11px] font-semibold text-[var(--muted)] sm:block">
              <span className="sm:hidden">إلى</span>
              <input type="time" name={`end_${index}`} defaultValue={(saved?.end_time || defaultEnd).slice(0, 5)} className="form-control h-9 min-h-9 py-1 text-xs" aria-label={`نهاية ${day}`} />
            </label>
          </div>
        );
      })}
    </div>
  );
}
