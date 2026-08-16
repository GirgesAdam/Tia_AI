import { Bot, Building2, Sparkles } from "lucide-react";
import { createWorkspaceAction } from "./actions";

export default function OnboardingPage(){
  return <main className="grid min-h-screen place-items-center bg-[var(--surface-2)] p-5" dir="rtl">
    <div className="w-full max-w-xl rounded-3xl border border-[var(--border)] bg-white p-7 shadow-sm">
      <div className="mb-7 flex items-center gap-3"><span className="grid size-12 place-items-center rounded-2xl bg-[var(--accent)] text-white"><Bot/></span><div><h1 className="text-2xl font-black">ابدأ Workspace جديدة</h1><p className="text-sm text-[var(--muted)]">Tia هتستخدمها كحد فاصل كامل لبيانات العيادة.</p></div></div>
      <div className="mb-6 rounded-2xl bg-teal-50 p-4 text-sm text-teal-900"><Sparkles className="mb-2" size={18}/>بعد الإنشاء هنمشي على الفروع، الخدمات، الدكاترة، المواعيد وإعدادات الحجز.</div>
      <form action={createWorkspaceAction} className="space-y-4">
        <label className="block text-sm font-bold">اسم العيادة<input name="name" required minLength={2} className="mt-1 w-full rounded-xl border border-[var(--border)] px-3 py-2.5" placeholder="مثال: Tia Clinic"/></label>
        <label className="block text-sm font-bold">Slug بالإنجليزي<input name="slug" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" className="mt-1 w-full rounded-xl border border-[var(--border)] px-3 py-2.5" placeholder="tia-clinic"/></label>
        <label className="block text-sm font-bold">Timezone<select name="timezone" defaultValue="Africa/Cairo" className="mt-1 w-full rounded-xl border border-[var(--border)] px-3 py-2.5"><option value="Africa/Cairo">Africa/Cairo</option><option value="Asia/Riyadh">Asia/Riyadh</option><option value="Asia/Dubai">Asia/Dubai</option></select></label>
        <button className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent)] font-bold text-white"><Building2 size={18}/>إنشاء Workspace</button>
      </form>
    </div>
  </main>
}
