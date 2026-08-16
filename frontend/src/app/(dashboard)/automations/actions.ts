"use server"; import { revalidatePath } from "next/cache"; import { tiaRequest } from "@/lib/tia/api";
export async function toggleAutomation(formData:FormData){const id=String(formData.get("rule_id"));const enabled=String(formData.get("enabled"))==="true";await tiaRequest(`/automations/rules/${id}`,{method:"PATCH",body:JSON.stringify({enabled})});revalidatePath("/automations");}
