import Link from "next/link";
import { CheckCircle2, Clock3, Database } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { ClinicSetupV2Snapshot } from "@/lib/clinic-setup-v2-types";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import { ClinicSetupImporter } from "./setup-importer";

export default async function SetupPage() {
  const [setup, ctx] = await Promise.all([
    tiaRequest<ClinicSetupV2Snapshot>("/clinic/setup-v2"),
    getAppContext(),
  ]);
  const admin = ctx.workspace.role === "admin";

  return (
    <>
      <PageHeader
        title="إعدادات العيادة"
        description="ارفع Excel أو أدخل البيانات يدويًا، راجعها ثم احفظها قبل الانتقال للخطوة التالية."
        action={<Link href="/knowledge" className={buttonVariants({ variant: "outline" })}><Database size={16} /> معلومات Tia</Link>}
      />

      <Card className="mb-5 border-teal-200 bg-teal-50/50">
        <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              {setup.readiness.ready ? <CheckCircle2 size={20} className="text-emerald-700" /> : <Clock3 size={20} className="text-amber-700" />}
              <b className="text-lg">{setup.readiness.ready ? "Tia جاهزة للحجز" : `اكتمال الإعداد ${setup.readiness.progress_percent}%`}</b>
              <Badge tone={setup.readiness.ready ? "green" : "yellow"}>{setup.readiness.ready ? "جاهزة" : "إعداد"}</Badge>
            </div>
            {!setup.readiness.ready && <p className="mt-2 text-sm text-[var(--muted)]">{setup.readiness.missing.join(" • ")}</p>}
            <p className="mt-2 text-xs text-[var(--muted)]">الخانات تحت تبدأ فاضية. تقدر تحمل البيانات المحفوظة للتعديل أو ترفع Excel جديد.</p>
          </div>
        </CardContent>
      </Card>

      {admin ? (
        <ClinicSetupImporter initialSetup={setup} />
      ) : (
        <Card><CardContent className="p-5 text-sm text-[var(--muted)]">إعدادات العيادة متاحة للأدمن فقط.</CardContent></Card>
      )}
    </>
  );
}
