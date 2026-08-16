import Link from "next/link";
import { Activity, Bot, CalendarDays, ContactRound, Inbox, LogOut, MessageCircleMore, Settings2, UsersRound, Workflow } from "lucide-react";
import type { MeResponse, WorkspaceAccess } from "@/lib/types";
import { initials } from "@/lib/format";
import { switchWorkspace, logoutAction } from "@/app/(dashboard)/actions";

const items=[
  ["/dashboard","نظرة عامة",Activity],["/inbox","Team Inbox",Inbox],["/appointments","الحجوزات",CalendarDays],
  ["/patients","العملاء",ContactRound],["/setup","إعداد العيادة",Settings2],["/automations","Automations",Workflow],["/channels","Channels",MessageCircleMore],
] as const;
export function DashboardShell({children,me,workspace}:{children:React.ReactNode;me:MeResponse;workspace:WorkspaceAccess}){
  return <div className="min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
    <aside className="hidden min-h-screen border-l border-slate-800 bg-[#142322] text-white lg:flex lg:flex-col lg:sticky lg:top-0 lg:h-screen">
      <div className="flex h-20 items-center gap-3 border-b border-white/10 px-6"><span className="grid size-10 place-items-center rounded-xl bg-teal-600"><Bot size={20}/></span><div><div className="font-black">Tia AI</div><div className="text-xs text-slate-400">Clinic workspace</div></div></div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-4">{items.map(([href,label,Icon])=><Link key={href} href={href} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-white/8 hover:text-white"><Icon size={18}/>{label}</Link>)}{workspace.role==="admin"&&<Link href="/team" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-white/8 hover:text-white"><UsersRound size={18}/>الفريق</Link>}</nav>
      <div className="border-t border-white/10 p-4"><form action={logoutAction}><button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-300 hover:bg-white/8"><LogOut size={17}/>تسجيل الخروج</button></form></div>
    </aside>
    <div className="min-w-0"><header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b border-[var(--border)] bg-white/90 px-4 backdrop-blur md:px-7"><div className="flex items-center gap-3 lg:hidden"><span className="grid size-9 place-items-center rounded-xl bg-[var(--accent)] text-white"><Bot size={18}/></span><b>Tia AI</b></div><form action={switchWorkspace} className="hidden md:block"><select name="workspace_id" defaultValue={workspace.workspace_id} className="rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm font-semibold" aria-label="Workspace"><option value={workspace.workspace_id}>{workspace.workspace_name} · {workspace.role}</option>{me.workspaces.filter(w=>w.workspace_id!==workspace.workspace_id).map(w=><option key={w.workspace_id} value={w.workspace_id}>{w.workspace_name} · {w.role}</option>)}</select><button className="ms-2 rounded-lg bg-[var(--surface-2)] px-3 py-2 text-xs font-semibold">تبديل</button></form><div className="flex items-center gap-3"><div className="text-left"><div className="text-sm font-bold">{me.user.full_name||me.user.email}</div><div className="text-xs text-[var(--muted)]">{workspace.role}</div></div><div className="grid size-10 place-items-center rounded-full bg-teal-50 text-sm font-black text-teal-700">{initials(me.user.full_name,me.user.email)}</div></div></header>
      <div className="border-b border-[var(--border)] bg-white px-4 py-2 lg:hidden"><div className="flex gap-2 overflow-x-auto">{items.map(([href,label])=><Link key={href} href={href} className="whitespace-nowrap rounded-lg bg-[var(--surface-2)] px-3 py-2 text-xs font-semibold">{label}</Link>)}</div></div>
      <main className="p-4 md:p-7">{children}</main>
    </div>
  </div>;
}
