import { Bot, Building2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { createWorkspaceAction } from "./actions";

export default function OnboardingPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--bg)] p-5 sm:p-8" dir="rtl">
      <div className="w-full max-w-xl rounded-3xl border border-[var(--border)] bg-white p-6 shadow-[0_16px_50px_rgba(15,23,42,.06)] sm:p-8">
        <div className="mb-7 flex items-start gap-3">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[var(--accent)] text-white shadow-[0_6px_16px_rgba(15,118,110,.18)]"><Bot /></span>
          <div>
            <h1 className="text-2xl font-black tracking-tight text-slate-950">إضافة عيادة جديدة</h1>
            <p className="mt-1 text-sm leading-6 text-[var(--muted)]">ابدأ بالمعلومات الأساسية، وبعدها تقدر تكمل إعداد التشغيل والبيانات خطوة بخطوة.</p>
          </div>
        </div>

        <div className="mb-6 rounded-2xl border border-teal-100 bg-teal-50/70 p-4 text-sm leading-6 text-teal-950">
          <Sparkles className="mb-2 text-teal-700" size={18} />
          بعد الإنشاء تقدر تضيف الفروع والخدمات والدكاترة ومواعيد العمل، أو تستورد بيانات العيادة الحالية.
        </div>

        <form action={createWorkspaceAction} className="space-y-5">
          <label className="block text-sm font-bold text-slate-800">
            اسم العيادة
            <input name="name" required minLength={2} className="form-control mt-1.5" placeholder="مثال: Tia Clinic" />
          </label>
          <label className="block text-sm font-bold text-slate-800">
            المنطقة الزمنية
            <select name="timezone" defaultValue="Africa/Cairo" className="form-control mt-1.5">
              <option value="Africa/Cairo">القاهرة</option>
              <option value="Asia/Riyadh">الرياض</option>
              <option value="Asia/Dubai">دبي</option>
            </select>
          </label>
          <Button className="w-full" size="lg">
            <Building2 size={18} /> إنشاء العيادة
          </Button>
        </form>
      </div>
    </main>
  );
}
