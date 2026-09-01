import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
}) {
  return (
    <div className="px-5 py-14 text-center sm:py-16">
      <span className="mx-auto grid size-12 place-items-center rounded-2xl border border-slate-200 bg-slate-50 text-slate-500 shadow-[0_1px_1px_rgba(15,23,42,.02)]">
        <Icon size={20} />
      </span>
      <div className="mt-4 text-sm font-black text-slate-900">{title}</div>
      {description && <p className="mx-auto mt-1.5 max-w-md text-xs leading-6 text-[var(--muted)]">{description}</p>}
    </div>
  );
}
