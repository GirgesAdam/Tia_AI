import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getMe } from "@/lib/tia/api";

export async function getAppContext() {
  const me = await getMe();
  if (!me.workspaces.length) redirect("/onboarding");
  const cookieStore = await cookies();
  const selectedId = cookieStore.get("tia_workspace_id")?.value;
  const workspace = me.workspaces.find((item) => item.workspace_id === selectedId);
  if (!workspace) redirect(`/workspace/activate?id=${encodeURIComponent(me.workspaces[0].workspace_id)}`);
  return { me, workspace };
}
