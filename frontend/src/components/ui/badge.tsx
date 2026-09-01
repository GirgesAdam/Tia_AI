import { cn } from "@/lib/utils";

const styles = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/15",
  yellow: "bg-amber-50 text-amber-800 ring-amber-600/15",
  red: "bg-rose-50 text-rose-700 ring-rose-600/15",
  blue: "bg-sky-50 text-sky-700 ring-sky-600/15",
  gray: "bg-slate-50 text-slate-600 ring-slate-500/15",
  purple: "bg-violet-50 text-violet-700 ring-violet-600/15",
} as const;

export function Badge({
  children,
  tone = "gray",
  className,
}: {
  children: React.ReactNode;
  tone?: keyof typeof styles;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold leading-5 ring-1 ring-inset",
        styles[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
