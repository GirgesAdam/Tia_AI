import type { EmailOtpType } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}

function authError(request: NextRequest) {
  return NextResponse.redirect(
    new URL(
      `/login?error=${encodeURIComponent("تعذر تأكيد الرابط. اطلب رابط جديد وحاول مرة أخرى.")}`,
      request.url,
    ),
  );
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const code = params.get("code");
  const tokenHash = params.get("token_hash");
  const type = params.get("type") as EmailOtpType | null;
  const next = safeNext(params.get("next"));
  const supabase = await createClient();

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) return authError(request);
    return NextResponse.redirect(new URL(next, request.url));
  }

  if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    if (error) return authError(request);
    return NextResponse.redirect(new URL(next, request.url));
  }

  return NextResponse.redirect(
    new URL(
      `/login?error=${encodeURIComponent("رابط الدخول غير مكتمل أو انتهت صلاحيته.")}`,
      request.url,
    ),
  );
}
