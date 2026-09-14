"use server";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export async function resetPasswordAction(formData: FormData) {
  const password = String(formData.get("password") || "");
  const confirmPassword = String(formData.get("confirm_password") || "");

  if (password.length < 8) {
    redirect(`/reset-password?error=${encodeURIComponent("كلمة المرور لازم تكون 8 حروف على الأقل.")}`);
  }
  if (password !== confirmPassword) {
    redirect(`/reset-password?error=${encodeURIComponent("كلمتا المرور غير متطابقتين.")}`);
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.updateUser({ password });
  if (error) {
    redirect(`/reset-password?error=${encodeURIComponent("تعذر تحديث كلمة المرور. اطلب رابط استعادة جديد وحاول مرة أخرى.")}`);
  }

  redirect(`/login?error=${encodeURIComponent("تم تحديث كلمة المرور. سجل دخولك بالكلمة الجديدة.")}`);
}
