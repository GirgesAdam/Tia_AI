import { Bot, CalendarCheck2, MessagesSquare, ShieldCheck } from "lucide-react";
import { loginAction } from "./actions";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default async function LoginPage({searchParams}:{searchParams:Promise<{error?:string}>}){
  const {error} = await searchParams;
  return <main className="grid min-h-screen lg:grid-cols-[1.05fr_.95fr]">
    <section className="hidden bg-[#102a2a] p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div className="flex items-center gap-3 text-xl font-bold"><span className="grid size-11 place-items-center rounded-2xl bg-white/10"><Bot/></span>Tia AI</div>
      <div className="max-w-xl"><p className="mb-4 text-sm font-semibold text-teal-200">CLINIC OPERATIONS + AI</p><h1 className="text-5xl font-black leading-[1.2]">كل شغل العيادة،<br/>في مكان واحد.</h1><p className="mt-6 max-w-lg text-lg leading-8 text-slate-300">محادثات العملاء، الحجوزات، الـCRM، التحويل للفريق، والـautomations — وكل تنفيذ مربوط بالداتا الحقيقية.</p></div>
      <div className="grid grid-cols-3 gap-3 text-sm text-slate-300"><div className="rounded-2xl bg-white/5 p-4"><MessagesSquare className="mb-3 text-teal-300"/>Team Inbox</div><div className="rounded-2xl bg-white/5 p-4"><CalendarCheck2 className="mb-3 text-teal-300"/>Booking</div><div className="rounded-2xl bg-white/5 p-4"><ShieldCheck className="mb-3 text-teal-300"/>Workspace RBAC</div></div>
    </section>
    <section className="flex items-center justify-center p-6 sm:p-12"><div className="w-full max-w-md"><div className="mb-9 lg:hidden"><div className="flex items-center gap-3 text-xl font-bold"><span className="grid size-10 place-items-center rounded-xl bg-[var(--accent)] text-white"><Bot size={20}/></span>Tia AI</div></div><h2 className="text-3xl font-black">أهلاً بيك</h2><p className="mt-2 text-sm text-[var(--muted)]">ادخل بحساب Supabase الخاص بفريق العيادة.</p>{error && <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}<form action={loginAction} className="mt-7 space-y-4"><label className="block space-y-2"><span className="text-sm font-semibold">الإيميل</span><Input name="email" type="email" autoComplete="email" required placeholder="name@clinic.com" dir="ltr"/></label><label className="block space-y-2"><span className="text-sm font-semibold">الباسورد</span><Input name="password" type="password" autoComplete="current-password" required dir="ltr"/></label><Button className="mt-2 w-full" size="lg">تسجيل الدخول</Button></form><p className="mt-6 text-center text-xs text-[var(--muted)]">Tia AI لا تتصل بقاعدة بيانات Supabase من الواجهة مباشرة؛ كل بيانات العيادة بتمر عبر FastAPI.</p></div></section>
  </main>;
}
