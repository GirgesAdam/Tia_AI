"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef } from "react";
import {
  Banknote,
  BarChart3,
  BotMessageSquare,
  CalendarDays,
  ContactRound,
  History,
  Inbox,
  ListTodo,
  Menu,
  PackageSearch,
  Settings2,
  Sparkles,
  Stethoscope,
  Tags,
  UsersRound,
  Workflow,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

const demoEnabled = process.env.NEXT_PUBLIC_TIA_DEMO_ENABLED === "true";

const primaryItems = [
  { href: "/dashboard", label: "الرئيسية", icon: Sparkles },
  { href: "/inbox", label: "الرسائل", icon: Inbox },
  { href: "/appointments", label: "المواعيد", icon: CalendarDays },
  { href: "/doctors", label: "الدكاترة", icon: Stethoscope },
  { href: "/patients", label: "العملاء", icon: ContactRound },
  { href: "/tasks", label: "المتابعات", icon: ListTodo },
  { href: "/analytics", label: "التقارير", icon: BarChart3 },
  { href: "/finance", label: "المالية", icon: Banknote },
  ...(demoEnabled ? [{ href: "/agent-demo", label: "اختبر Tia", icon: BotMessageSquare }] : []),
] as const;

const adminItems = [
  { href: "/services", label: "الخدمات والأسعار", icon: Tags },
  { href: "/inventory", label: "المخزن", icon: PackageSearch },
  { href: "/setup", label: "إعدادات العيادة", icon: Settings2 },
  { href: "/automations", label: "الرسائل التلقائية", icon: Workflow },
  { href: "/team", label: "الفريق", icon: UsersRound },
  { href: "/activity", label: "سجل النشاط", icon: History },
] as const;

const mobilePrimaryHrefs = new Set(["/dashboard", "/inbox", "/appointments", "/patients"]);

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
    <nav className="flex-1 overflow-y-auto px-3 py-5 scrollbar-thin" aria-label="التنقل الرئيسي">
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

function MobileNavLink({ href, label, Icon, onNavigate }: { href: string; label: string; Icon: typeof Sparkles; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = activeFor(pathname, href);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      className={cn(
        "flex min-h-12 items-center gap-3 rounded-xl px-3 text-sm font-bold transition",
        active ? "bg-teal-50 text-teal-900" : "text-slate-700 hover:bg-slate-50",
      )}
    >
      <Icon size={18} className={active ? "text-teal-700" : "text-slate-500"} />
      {label}
    </Link>
  );
}

export function MobileNavigation({ isAdmin }: { isAdmin: boolean }) {
  const pathname = usePathname();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const mobilePrimary = primaryItems.filter((item) => mobilePrimaryHrefs.has(item.href));
  const morePrimary = primaryItems.filter((item) => !mobilePrimaryHrefs.has(item.href));
  const moreActive = [...morePrimary, ...(isAdmin ? adminItems : [])].some((item) => activeFor(pathname, item.href));

  const close = () => dialogRef.current?.close();

  return (
    <>
      <nav
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-slate-200/90 bg-white/95 px-2 pb-[max(.5rem,env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_24px_rgba(15,23,42,.05)] backdrop-blur-xl lg:hidden"
        aria-label="التنقل الرئيسي"
      >
        {mobilePrimary.map(({ href, label, icon: Icon }) => {
          const active = activeFor(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-12 flex-col items-center justify-center gap-1 rounded-xl px-1 text-[11px] font-bold transition",
                active ? "bg-teal-50 text-teal-800" : "text-slate-500 hover:bg-slate-50 hover:text-slate-800",
              )}
            >
              <Icon size={18} strokeWidth={active ? 2.2 : 1.8} />
              <span className="max-w-full truncate">{label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => dialogRef.current?.showModal()}
          aria-haspopup="dialog"
          className={cn(
            "flex min-h-12 flex-col items-center justify-center gap-1 rounded-xl px-1 text-[11px] font-bold transition",
            moreActive ? "bg-teal-50 text-teal-800" : "text-slate-500 hover:bg-slate-50 hover:text-slate-800",
          )}
        >
          <Menu size={18} strokeWidth={moreActive ? 2.2 : 1.8} />
          المزيد
        </button>
      </nav>

      <dialog
        ref={dialogRef}
        aria-labelledby="mobile-more-title"
        className="m-0 h-full max-h-none w-full max-w-none bg-transparent p-0 backdrop:bg-slate-950/35 lg:hidden"
        onClick={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      >
        <div className="absolute inset-x-0 bottom-0 max-h-[82vh] overflow-y-auto rounded-t-3xl bg-white p-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-2xl">
          <div className="mb-4 flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <div id="mobile-more-title" className="font-black text-slate-950">المزيد</div>
              <div className="mt-0.5 text-xs text-slate-500">باقي أدوات العيادة والإدارة</div>
            </div>
            <button
              type="button"
              onClick={close}
              className="grid size-10 place-items-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
              aria-label="إغلاق القائمة"
            >
              <X size={18} />
            </button>
          </div>

          <div className="section-kicker px-2 pb-2">العمل اليومي</div>
          <div className="space-y-1">
            {morePrimary.map(({ href, label, icon }) => (
              <MobileNavLink key={href} href={href} label={label} Icon={icon} onNavigate={close} />
            ))}
          </div>

          {isAdmin && (
            <>
              <div className="my-4 border-t border-slate-100" />
              <div className="section-kicker px-2 pb-2">الإدارة</div>
              <div className="space-y-1">
                {adminItems.map(({ href, label, icon }) => (
                  <MobileNavLink key={href} href={href} label={label} Icon={icon} onNavigate={close} />
                ))}
              </div>
            </>
          )}
        </div>
      </dialog>
    </>
  );
}
