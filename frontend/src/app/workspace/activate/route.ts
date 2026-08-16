import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { getMe } from "@/lib/tia/api";
export async function GET(request: NextRequest){
  const id=request.nextUrl.searchParams.get("id"); const me=await getMe();
  const allowed=me.workspaces.some((w)=>w.workspace_id===id); if(!id||!allowed) return NextResponse.redirect(new URL("/dashboard",request.url));
  const store=await cookies(); store.set("tia_workspace_id",id,{httpOnly:true,sameSite:"lax",secure:process.env.NODE_ENV==="production",path:"/",maxAge:60*60*24*365});
  return NextResponse.redirect(new URL("/dashboard",request.url));
}
