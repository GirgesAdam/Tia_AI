import { redirect } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { WorkspaceMember } from "@/lib/types";
import { changeRole, inviteMember } from "./actions";

const roleLabels = { admin: "مدير", member: "عضو فريق" } as const;

export default async function TeamPage() {
  const ctx = await getAppContext();
  if (ctx.workspace.role !== "admin") redirect("/dashboard");
  const members = await tiaRequest<WorkspaceMember[]>("/auth/workspace/members");

  return (
    <>
      <PageHeader
        title="الفريق"
        description="إدارة أعضاء فريق العيادة وتحديد من يملك صلاحيات الإدارة."
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader><CardTitle>أعضاء الفريق</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {members.map((member) => (
              <div key={member.membership_id} className="flex flex-col gap-3 rounded-xl border border-[var(--border)] p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="truncate font-bold">{member.full_name || member.email}</div>
                  <div className="truncate text-xs text-[var(--muted)]">{member.email}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={member.role === "admin" ? "purple" : "gray"}>{roleLabels[member.role]}</Badge>
                  <form action={changeRole} className="flex gap-2">
                    <input type="hidden" name="membership_id" value={member.membership_id} />
                    <select name="role" defaultValue={member.role} className="rounded-lg border border-[var(--border)] bg-white px-2 py-1 text-xs">
                      <option value="member">عضو فريق</option>
                      <option value="admin">مدير</option>
                    </select>
                    <Button size="sm" variant="outline">حفظ</Button>
                  </form>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>دعوة عضو جديد</CardTitle></CardHeader>
          <CardContent>
            <form action={inviteMember} className="space-y-3">
              <Input name="email" type="email" placeholder="member@clinic.com" required dir="ltr" />
              <select name="role" defaultValue="member" className="form-control">
                <option value="member">عضو فريق</option>
                <option value="admin">مدير</option>
              </select>
              <Button className="w-full">إرسال الدعوة</Button>
            </form>
            <p className="mt-3 text-xs leading-5 text-[var(--muted)]">يظل لازم يكون فيه مدير واحد على الأقل للعيادة.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
