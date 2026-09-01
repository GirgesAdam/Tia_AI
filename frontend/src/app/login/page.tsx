import { Bot, CalendarCheck2, MessagesSquare, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { demoLoginAction, loginAction } from "./actions";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  const demoEnabled = process.env.TIA_DEMO_ENABLED === "true";
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.05fr_.95fr]">
      <section className="hidden bg-[#102a2a] p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3 text-xl font-bold">
          <span className="grid size-11 place-items-center rounded-2xl bg-white/10"><Bot /></span>
          Tia
        </div>
        <div className="max-w-xl">
          <p className="mb-4 text-sm font-semibold text-teal-200">إدارة العيادة وخدمة العملاء</p>
          <h1 className="text-5xl font-black leading-[1.2]">كل شغل العيادة،<br />في مكان واحد.</h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-slate-300">
            رسائل العملاء، المواعيد، المتابعات والتقارير — مع Tia تساعد الفريق في الشغل اليومي من غير تعقيد.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 text-sm text-slate-300">
          <div className="rounded-2xl bg-white/5 p-4"><MessagesSquare className="mb-3 text-teal-300" />الرسائل</div>
          <div className="rounded-2xl bg-white/5 p-4"><CalendarCheck2 className="mb-3 text-teal-300" />المواعيد</div>
          <div className="rounded-2xl bg-white/5 p-4"><ShieldCheck className="mb-3 text-teal-300" />صلاحيات الفريق</div>
        </div>
      </section>

      <section className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-md">
          <div className="mb-9 lg:hidden">
            <div className="flex items-center gap-3 text-xl font-bold">
              <span className="grid size-10 place-items-center rounded-xl bg-[var(--accent)] text-white"><Bot size={20} /></span>
              Tia
            </div>
          </div>
          <h2 className="text-3xl font-black">تسجيل الدخول</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">استخدم حسابك المسجل ضمن فريق العيادة.</p>
          {error && <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
          {demoEnabled && (
            <form action={demoLoginAction} className="mt-7">
              <Button type="submit" className="w-full" size="lg">
                <Bot size={18} /> جرّب نسخة الـAdmin Demo
              </Button>
              <p className="mt-2 text-center text-xs leading-5 text-[var(--muted)]">
                دخول فوري إلى عيادة تجريبية معزولة — بدون الحاجة لبيانات تسجيل.
              </p>
            </form>
          )}

          {demoEnabled && <div className="my-5 flex items-center gap-3 text-xs text-slate-400"><span className="h-px flex-1 bg-slate-200" />أو حسابك<span className="h-px flex-1 bg-slate-200" /></div>}

          <form action={loginAction} className={demoEnabled ? "space-y-4" : "mt-7 space-y-4"}>
            <label className="block space-y-2">
              <span className="text-sm font-semibold">البريد الإلكتروني</span>
              <Input name="email" type="email" autoComplete="email" required placeholder="name@clinic.com" dir="ltr" />
            </label>
            <label className="block space-y-2">
              <span className="text-sm font-semibold">كلمة المرور</span>
              <Input name="password" type="password" autoComplete="current-password" required dir="ltr" />
            </label>
            <Button className="mt-2 w-full" size="lg">تسجيل الدخول</Button>
          </form>
          <p className="mt-6 text-center text-xs leading-5 text-[var(--muted)]">بيانات العيادة محمية ولا تظهر إلا للأعضاء المصرح لهم.</p>
        </div>
      </section>
    </main>
  );
}
