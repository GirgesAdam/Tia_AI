"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getMe } from "@/lib/tia/api";
import { createClient } from "@/lib/supabase/server";
export async function switchWorkspace(formData:FormData){const id=String(formData.get("workspace_id")||"");const me=await getMe();if(!me.workspaces.some(w=>w.workspace_id===id)) throw new Error("Workspace غير متاح.");const store=await cookies();store.set("tia_workspace_id",id,{httpOnly:true,sameSite:"lax",secure:process.env.NODE_ENV==="production",path:"/",maxAge:60*60*24*365});redirect("/dashboard");}
export async function logoutAction(){const supabase=await createClient();await supabase.auth.signOut();const store=await cookies();store.delete("tia_workspace_id");redirect("/login");}
