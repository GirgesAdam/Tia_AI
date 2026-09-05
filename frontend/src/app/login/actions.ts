"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

async function signInAndOpenWorkspace(email: string, password: string, destination = "/dashboard") {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error || !data.session?.access_token) {
    redirect(`/login?error=${encodeURIComponent("الإيميل أو الباسورد مش صحيح.")}`);
  }

  const apiUrl = (process.env.TIA_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const response = await fetch(`${apiUrl}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${data.session.access_token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    await supabase.auth.signOut();
    redirect(`/login?error=${encodeURIComponent("تعذر فتح حساب العيادة. راجع مسؤول النظام.")}`);
  }

  const me = (await response.json()) as { workspaces: Array<{ workspace_id: string }> };
  if (!me.workspaces.length) {
    await supabase.auth.signOut();
    redirect(`/login?error=${encodeURIComponent("الحساب غير مرتبط بأي عيادة حتى الآن.")}`);
  }

  const cookieStore = await cookies();
  cookieStore.set("tia_workspace_id", me.workspaces[0].workspace_id, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
  redirect(destination);
}

export async function loginAction(formData: FormData) {
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");
  await signInAndOpenWorkspace(email, password);
}

export async function demoLoginAction() {
  if (process.env.TIA_DEMO_ENABLED !== "true") {
    redirect(`/login?error=${encodeURIComponent("نسخة الـDemo غير مفعلة على هذه البيئة.")}`);
  }
  const email = process.env.TIA_DEMO_EMAIL?.trim();
  const password = process.env.TIA_DEMO_PASSWORD || "";
  if (!email || !password) {
    redirect(`/login?error=${encodeURIComponent("حساب الـDemo غير مجهز بعد.")}`);
  }
  await signInAndOpenWorkspace(email, password, "/demo");
}
