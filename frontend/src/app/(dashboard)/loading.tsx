export default function DashboardLoading() {
  return (
    <div className="animate-pulse space-y-6" role="status" aria-live="polite" aria-label="جارٍ تحميل الصفحة">
      <span className="sr-only">جارٍ تحميل بيانات الصفحة</span>
      <div className="space-y-2" aria-hidden="true">
        <div className="h-8 w-44 rounded-lg bg-slate-200" />
        <div className="h-4 w-full max-w-xl rounded bg-slate-100" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-32 rounded-2xl border border-slate-200 bg-white" />
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.3fr_.7fr]" aria-hidden="true">
        <div className="h-80 rounded-2xl border border-slate-200 bg-white" />
        <div className="h-80 rounded-2xl border border-slate-200 bg-white" />
      </div>
    </div>
  );
}
