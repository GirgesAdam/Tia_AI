import Link from "next/link";
import { ArrowRight, Download, History } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { HistoricalBatch } from "@/lib/clinic-setup-v2-types";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import { HistoricalImportUploader } from "./history-uploader";

const statusLabel: Record<HistoricalBatch["status"], string> = {
  preview_ready: "تم الفحص",
  importing: "جاري الاستيراد",
  imported: "مكتمل",
  failed: "لم يكتمل",
};

export default async function HistoricalImportPage() {
  const ctx = await getAppContext();
  const admin = ctx.workspace.role === "admin";
  const data = await tiaRequest<{ batches: HistoricalBatch[] }>("/clinic/history/batches");
  const activeBatch = data.batches.find((batch) => ["importing", "preview_ready", "failed"].includes(batch.status)) || null;

  return (
    <>
      <PageHeader
        title="البيانات التاريخية"
        description="ميزة اختيارية لنقل العملاء والمواعيد والمدفوعات والباقات القديمة إلى Tia بعد تجهيز العيادة."
        action={<Link href="/setup" className={buttonVariants({ variant: "outline" })}><ArrowRight size={16} /> إعدادات العيادة</Link>}
      />

      <Card className="mb-5 border-slate-200 bg-slate-50/70">
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div><b>Tia Import Contract v1</b><p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--muted)]">استخدم القالب الثابت بدل Mapping Wizard. العملة EGP، لا يوجد Email أو Gender للعملاء، ووقت نهاية الموعد يُحسب من مدة الخدمة.</p></div>
          <a href="/api/clinic-history-template" className={buttonVariants({ variant: "outline" })}><Download size={16} /> تحميل القالب</a>
        </CardContent>
      </Card>

      {admin ? <HistoricalImportUploader initialBatch={activeBatch} /> : <Card><CardContent className="p-5 text-sm text-[var(--muted)]">الاستيراد متاح لمدير العيادة فقط.</CardContent></Card>}

      <Card className="mt-5">
        <CardContent className="p-5">
          <div className="mb-4 flex items-center gap-2"><History size={18} /><b>آخر عمليات الاستيراد</b></div>
          {data.batches.length ? <div className="space-y-2">{data.batches.map((batch) => <div key={batch.batch_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] p-3"><div><div className="text-sm font-bold">{batch.source_name}</div><div className="mt-1 text-xs text-[var(--muted)]">{batch.mode === "append" ? "إضافة" : "استبدال الاستيرادات السابقة"}</div></div><Badge tone={batch.status === "imported" ? "green" : batch.status === "failed" ? "red" : "yellow"}>{statusLabel[batch.status]}</Badge></div>)}</div> : <p className="text-sm text-[var(--muted)]">لا توجد عمليات استيراد تاريخية حتى الآن.</p>}
        </CardContent>
      </Card>
    </>
  );
}
