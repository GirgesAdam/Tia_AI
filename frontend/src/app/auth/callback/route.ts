import { NextRequest, NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const next = safeNext(request.nextUrl.searchParams.get("next"));

  if (!code) {
    return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent("رابط الدخول غير مكتمل أو انتهت صلاحيته.")}`, request.url));
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent("تعذر تأكيد الرابط. اطلب رابط جديد وحاول مرة أخرى.")}`, request.url));
  }

  return NextResponse.redirect(new URL(next, request.url));
}
