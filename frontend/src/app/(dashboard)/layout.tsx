import { DashboardShell } from "@/components/dashboard-shell";
import { getAppContext } from "@/lib/tia/workspace";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { me, workspace } = await getAppContext();
  const demoMode = "is_demo" in workspace && workspace.is_demo === true;
  return <DashboardShell me={me} workspace={workspace} demoMode={demoMode}>{children}</DashboardShell>;
}
