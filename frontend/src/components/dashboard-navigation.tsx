"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Banknote,
  BarChart3,
  BotMessageSquare,
  CalendarDays,
  ContactRound,
  History,
  Inbox,
  ListTodo,
  MessageCircleMore,
  Settings2,
  Sparkles,
  UsersRound,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

const demoEnabled = process.env.NEXT_PUBLIC_TIA_DEMO_ENABLED === "true";

const primaryItems = [
  { href: "/dashboard", label: "الرئيسية", icon: Sparkles },
  { href: "/inbox", label: "الرسائل", icon: Inbox },
  { href: "/appointments", label: "المواعيد", icon: CalendarDays },
  { href: "/patients", label: "العملاء", icon: ContactRound },
  { href: "/tasks", label: "المتابعات", icon: ListTodo },
  { href: "/analytics", label: "التقارير", icon: BarChart3 },
  { href: "/finance", label: "المالية", icon: Banknote },
  ...(demoEnabled ? [{ href: "/agent-demo", label: "Test Tia", icon: BotMessageSquare }] : []),
] as const;

const adminItems = [
  { href: "/setup", label: "إعدادات العيادة", icon: Settings2 },
  { href: "/automations", label: "الأتمتة", icon: Workflow },
  { href: "/channels", label: "قنوات التواصل", icon: MessageCircleMore },
  { href: "/team", label: "الفريق", icon: UsersRound },
  { href: "/activity", label: "سجل النشاط", icon: History },
] as const;

function activeFor(pathname: string, href: string) {
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function DesktopNavItem({ href, label, Icon, active }: { href: string; label: string; Icon: typeof Sparkles; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition",
        active ? "bg-teal-50 text-teal-900" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
      )}
    >
      {active && <span className="absolute right-0 h-5 w-1 rounded-l-full bg-teal-700" />}
      <Icon size={18} strokeWidth={active ? 2.1 : 1.8} className={active ? "text-teal-700" : "text-slate-500 group-hover:text-slate-700"} />
      {label}
    </Link>
  );
}

export function DesktopNavigation({ isAdmin }: { isAdmin: boolean }) {
  const pathname = usePathname();
  return (
    <nav className="flex-1 overflow-y-auto px-3 py-5 scrollbar-thin">
      <div className="px-3 pb-2 text-[10px] font-black tracking-[0.08em] text-slate-400">العمل اليومي</div>
      <div className="space-y-1">
        {primaryItems.map(({ href, label, icon }) => (
          <DesktopNavItem key={href} href={href} label={label} Icon={icon} active={activeFor(pathname, href)} />
        ))}
      </div>

      {isAdmin && (
        <>
          <div className="mx-3 my-5 border-t border-slate-100" />
          <div className="px-3 pb-2 text-[10px] font-black tracking-[0.08em] text-slate-400">الإدارة</div>
          <div className="space-y-1">
            {adminItems.map(({ href, label, icon }) => (
              <DesktopNavItem key={href} href={href} label={label} Icon={icon} active={activeFor(pathname, href)} />
            ))}
          </div>
        </>
      )}
    </nav>
  );
}

export function MobileNavigation() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto px-3 py-2 scrollbar-thin" aria-label="التنقل الرئيسي">
      {primaryItems.map(({ href, label, icon: Icon }) => {
        const active = activeFor(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg px-3 text-xs font-bold transition",
              active ? "bg-teal-50 text-teal-800" : "text-slate-600 hover:bg-slate-50",
            )}
          >
            <Icon size={15} strokeWidth={active ? 2.1 : 1.8} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
