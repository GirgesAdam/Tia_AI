import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { MeResponse } from "@/lib/types";

const API_URL = (process.env.TIA_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export class TiaApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function accessToken() {
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  if (!claimsData?.claims?.sub) redirect("/login");
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token;
  if (!token) redirect("/login");
  return token;
}

async function parseError(response: Response) {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch { return `${response.status} ${response.statusText}`; }
}

export async function tiaRequest<T>(path: string, init: RequestInit = {}, options?: { workspace?: boolean }) {
  const token = await accessToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (options?.workspace !== false) {
    const cookieStore = await cookies();
    const workspaceId = cookieStore.get("tia_workspace_id")?.value;
    if (!workspaceId) throw new TiaApiError(409, "Workspace is not selected.");
    headers.set("X-Workspace-ID", workspaceId);
  }
  const response = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new TiaApiError(response.status, await parseError(response));
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export function getMe() {
  return tiaRequest<MeResponse>("/auth/me", {}, { workspace: false });
}
