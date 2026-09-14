import { LockKeyhole } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { resetPasswordAction } from "./actions";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--bg)] p-5 sm:p-8" dir="rtl">
      <div className="w-full max-w-md rounded-3xl border border-[var(--border)] bg-white p-6 shadow-[0_16px_50px_rgba(15,23,42,.06)] sm:p-8">
        <div className="mb-7 flex items-start gap-3">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[var(--accent)] text-white"><LockKeyhole /></span>
          <div>
            <h1 className="text-2xl font-black">كلمة مرور جديدة</h1>
            <p className="mt-1 text-sm leading-6 text-[var(--muted)]">اختار كلمة مرور جديدة للحساب، وبعدها ارجع وسجل دخولك بشكل طبيعي.</p>
          </div>
        </div>

        {error && <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

        <form action={resetPasswordAction} className="space-y-4">
          <label className="block space-y-2">
            <span className="text-sm font-semibold">كلمة المرور الجديدة</span>
            <Input name="password" type="password" autoComplete="new-password" required minLength={8} dir="ltr" />
          </label>
          <label className="block space-y-2">
            <span className="text-sm font-semibold">تأكيد كلمة المرور</span>
            <Input name="confirm_password" type="password" autoComplete="new-password" required minLength={8} dir="ltr" />
          </label>
          <Button className="w-full" size="lg">حفظ كلمة المرور</Button>
        </form>
      </div>
    </main>
  );
}
