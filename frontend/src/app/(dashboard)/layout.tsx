import { DashboardShell } from "@/components/dashboard-shell";
import { getAppContext } from "@/lib/tia/workspace";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { me, workspace } = await getAppContext();
  const demoMode = process.env.TIA_DEMO_ENABLED === "true";
  return <DashboardShell me={me} workspace={workspace} demoMode={demoMode}>{children}</DashboardShell>;
}
