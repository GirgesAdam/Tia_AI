import Link from "next/link";

import { cn } from "@/lib/utils";

export function FilterChip({
  href,
  active,
  children,
  className,
}: {
  href: string;
  active?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "inline-flex min-h-9 shrink-0 items-center justify-center rounded-lg border px-3 text-xs font-bold transition",
        active
          ? "border-teal-200 bg-teal-50 text-teal-800 shadow-[inset_0_0_0_1px_rgba(13,148,136,.04)]"
          : "border-transparent bg-transparent text-slate-600 hover:bg-slate-50 hover:text-slate-950",
        className,
      )}
    >
      {children}
    </Link>
  );
}
