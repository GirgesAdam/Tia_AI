import Link from "next/link";
import { CheckCircle2, Clock3, Database } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { ClinicKnowledgeBaseSnapshot } from "@/lib/clinic-knowledge-base-types";
import type { ClinicSetupV2Snapshot } from "@/lib/clinic-setup-v2-types";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";

import { ClinicSettingsPanel } from "./clinic-settings-panel";

export default async function SetupPage() {
  const [setup, knowledge, ctx] = await Promise.all([
    tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2"),
    tiaRequest<ClinicKnowledgeBaseSnapshot>("/clinic/knowledge-base"),
    getAppContext(),
  ]);
  const admin = ctx.workspace.role === "admin";

  return (
    <>
      <PageHeader
        title="إعدادات العيادة"
        description="مصدر بيانات العيادة ومعرفة Tia: معلومات العيادة، مواعيد وسياسة الحجز، الشرح الذي تستخدمه Tia، وربط البيانات القديمة."
        action={<Link href="/knowledge" className={buttonVariants({ variant: "outline" })}><Database size={16} /> عرض البيانات التشغيلية</Link>}
      />

      <Card className="mb-5 border-teal-200 bg-teal-50/50">
        <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              {setup.readiness.ready ? <CheckCircle2 size={20} className="text-emerald-700" /> : <Clock3 size={20} className="text-amber-700" />}
              <b className="text-lg">{setup.readiness.ready ? "بيانات الحجز الأساسية جاهزة" : `اكتمال البيانات التشغيلية ${setup.readiness.progress_percent}%`}</b>
              <Badge tone={setup.readiness.ready ? "green" : "yellow"}>{setup.readiness.ready ? "جاهزة" : "ناقص بيانات"}</Badge>
            </div>
            {!setup.readiness.ready && <p className="mt-2 text-sm text-[var(--muted)]">{setup.readiness.missing.join(" • ")}</p>}
            <p className="mt-2 text-xs text-[var(--muted)]">الخدمات والأسعار تُدار من صفحة الخدمات، والدكاترة ومواعيدهم من صفحة الدكاترة. الصفحة دي لا تكرر نفس البيانات.</p>
          </div>
        </CardContent>
      </Card>

      {admin ? (
        <ClinicSettingsPanel setup={setup} knowledge={knowledge.entries} />
      ) : (
        <Card><CardContent className="p-5 text-sm text-[var(--muted)]">إعدادات العيادة متاحة للأدمن فقط.</CardContent></Card>
      )}
    </>
  );
}
