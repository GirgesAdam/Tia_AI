import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  detail,
  icon: Icon,
  href,
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: LucideIcon;
  href?: string;
}) {
  const content = (
    <Card
      className={cn(
        "h-full overflow-hidden",
        href && "transition hover:-translate-y-px hover:border-teal-200 hover:shadow-[0_8px_24px_rgba(15,118,110,.06)]",
      )}
    >
      <CardContent className="flex h-full items-start justify-between gap-4 p-5 sm:p-5">
        <div className="min-w-0">
          <div className="text-[13px] font-bold text-[var(--muted)]">{label}</div>
          <div className="mt-2 text-[32px] font-black leading-none tracking-[-0.03em] text-slate-950">{value}</div>
          <div className="mt-3 text-xs leading-5 text-[var(--muted)]">{detail}</div>
        </div>
        <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-teal-100 bg-teal-50 text-teal-700">
          <Icon size={18} strokeWidth={1.9} />
        </span>
      </CardContent>
    </Card>
  );

  return href ? <Link href={href} className="block h-full">{content}</Link> : content;
}
