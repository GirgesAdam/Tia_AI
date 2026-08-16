"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { tiaRequest } from "@/lib/tia/api";

function slugify(value:string){
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
}

export async function createWorkspaceAction(formData:FormData){
  const name=String(formData.get("name")||"").trim();
  const requested=String(formData.get("slug")||"").trim();
  const slug=slugify(requested||name);
  const timezone=String(formData.get("timezone")||"Africa/Cairo");
  const created=await tiaRequest<{workspace_id:string}>("/onboarding/workspaces",{
    method:"POST",body:JSON.stringify({name,slug,timezone})
  },{workspace:false});
  const store=await cookies();
  store.set("tia_workspace_id",created.workspace_id,{httpOnly:true,sameSite:"lax",secure:process.env.NODE_ENV==="production",path:"/",maxAge:60*60*24*365});
  redirect("/setup");
}
