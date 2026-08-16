import { DashboardShell } from "@/components/dashboard-shell";
import { getAppContext } from "@/lib/tia/workspace";
export default async function DashboardLayout({children}:{children:React.ReactNode}){const {me,workspace}=await getAppContext();return <DashboardShell me={me} workspace={workspace}>{children}</DashboardShell>}
