import { Bot, LogOut } from "lucide-react";

import { logoutAction, switchWorkspace } from "@/app/(dashboard)/actions";
import { DesktopNavigation, MobileNavigation } from "@/components/dashboard-navigation";
import { Button } from "@/components/ui/button";
import { initials } from "@/lib/format";
import type { MeResponse, WorkspaceAccess } from "@/lib/types";

const roleLabels = { admin: "مدير", member: "عضو فريق" } as const;

export function DashboardShell({
  children,
  me,
  workspace,
  demoMode = false,
}: {
  children: React.ReactNode;
  me: MeResponse;
  workspace: WorkspaceAccess;
  demoMode?: boolean;
}) {
  const otherWorkspaces = me.workspaces.filter((item) => item.workspace_id !== workspace.workspace_id);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[256px_minmax(0,1fr)]">
      <aside className="hidden h-screen border-l border-slate-200/80 bg-white lg:sticky lg:top-0 lg:flex lg:flex-col">
        <div className="flex h-[76px] items-center gap-3 border-b border-slate-100 px-5">
          <span className="grid size-10 place-items-center rounded-xl bg-teal-700 text-white shadow-[0_4px_12px_rgba(15,118,110,.18)]">
            <Bot size={19} />
          </span>
          <div className="min-w-0">
            <div className="text-[17px] font-black tracking-[-0.02em] text-slate-950">Tia</div>
            <div className="mt-0.5 truncate text-[11px] font-semibold text-slate-500">{workspace.workspace_name}</div>
          </div>
        </div>

        <DesktopNavigation isAdmin={workspace.role === "admin"} />

        <div className="border-t border-slate-100 p-3">
          <form action={logoutAction}>
            <button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-slate-900">
              <LogOut size={17} />
              تسجيل الخروج
            </button>
          </form>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/92 backdrop-blur-xl">
          <div className="flex h-16 items-center justify-between gap-4 px-4 md:px-6 lg:h-[68px] lg:px-8">
            <div className="flex min-w-0 items-center gap-3 lg:hidden">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-teal-700 text-white shadow-sm">
                <Bot size={17} />
              </span>
              <div className="min-w-0">
                <div className="font-black tracking-tight">Tia</div>
                <div className="truncate text-[10px] font-semibold text-slate-500">{workspace.workspace_name}</div>
              </div>
            </div>

            <div className="hidden min-w-0 md:block">
              {me.workspaces.length > 1 ? (
                <form action={switchWorkspace} className="flex items-center gap-2">
                  <span className="text-[11px] font-bold text-slate-500">العيادة</span>
                  <select
                    name="workspace_id"
                    defaultValue={workspace.workspace_id}
                    className="h-9 max-w-72 rounded-lg border border-[var(--border)] bg-white px-3 text-sm font-semibold text-slate-800 outline-none transition hover:border-[var(--border-strong)] focus:border-teal-500 focus:ring-2 focus:ring-[var(--accent-ring)]"
                    aria-label="اختيار العيادة"
                  >
                    <option value={workspace.workspace_id}>{workspace.workspace_name}</option>
                    {otherWorkspaces.map((item) => (
                      <option key={item.workspace_id} value={item.workspace_id}>
                        {item.workspace_name}
                      </option>
                    ))}
                  </select>
                  <Button size="sm" variant="outline">تبديل</Button>
                </form>
              ) : (
                <div>
                  <div className="text-[10px] font-bold text-slate-400">العيادة</div>
                  <div className="mt-0.5 text-sm font-bold text-slate-800">{workspace.workspace_name}</div>
                </div>
              )}
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden text-left sm:block">
                <div className="max-w-52 truncate text-sm font-bold text-slate-900">{me.user.full_name || me.user.email}</div>
                <div className="mt-0.5 text-[11px] font-semibold text-slate-500">{roleLabels[workspace.role]}</div>
              </div>
              <div className="grid size-9 place-items-center rounded-full border border-teal-100 bg-teal-50 text-xs font-black text-teal-800">
                {initials(me.user.full_name, me.user.email)}
              </div>
            </div>
          </div>

          <div className="border-t border-slate-100 lg:hidden">
            <MobileNavigation />
          </div>
        </header>

        {demoMode && (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs font-semibold text-amber-950">
            Admin Demo · كل التعديلات والحجوزات هنا على بيانات تجريبية معزولة، والإرسال الخارجي متوقف.
          </div>
        )}
        <main className="mx-auto w-full max-w-[1440px] p-4 pb-24 md:p-6 md:pb-24 lg:p-8 lg:pb-20">{children}</main>
      </div>
    </div>
  );
}
