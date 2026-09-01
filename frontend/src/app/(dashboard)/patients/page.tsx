import Link from "next/link";
import { ChevronLeft, Phone, Search, UsersRound } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";
import { labelForSource, labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import type { Patient } from "@/lib/types";

export default async function PatientsPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  const patients = await tiaRequest<Patient[]>(`/crm/patients?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}`);

  return (
    <>
      <PageHeader title="العملاء" description="ابحث عن أي عميل وافتح ملفه لمراجعة بيانات التواصل والمواعيد والمتابعات." />

      <form className="mb-4 flex max-w-xl gap-2">
        <div className="relative flex-1">
          <Search className="absolute right-3 top-3.5 text-slate-400" size={16} />
          <Input name="q" defaultValue={q} placeholder="ابحث بالاسم أو رقم الهاتف أو البريد" className="pr-9" />
        </div>
        <Button type="submit" className="px-5">بحث</Button>
      </form>

      <Card>
        <CardContent className="p-0 sm:p-0">
          {patients.length ? (
            <>
              <div className="divide-y divide-[var(--border)] md:hidden">
                {patients.map((patient) => (
                  <Link key={patient.id} href={`/patients/${patient.id}`} className="block p-4 transition hover:bg-slate-50">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-black text-slate-950">{patient.first_name} {patient.last_name || ""}</div>
                        <div className="mt-1 inline-flex items-center gap-1.5 text-xs text-[var(--muted)]">
                          <Phone size={13} />
                          <span dir="ltr">{patient.phone || "بدون رقم هاتف"}</span>
                        </div>
                      </div>
                      <Badge tone={toneForStatus(patient.status)}>{labelForStatus(patient.status)}</Badge>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-xs">
                      <div><div className="text-[var(--muted)]">المصدر</div><div className="mt-1 font-bold text-slate-800">{labelForSource(patient.source)}</div></div>
                      <div><div className="text-[var(--muted)]">آخر تواصل</div><div className="mt-1 font-bold text-slate-800">{formatDateTime(patient.last_contact_at)}</div></div>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-xs text-[var(--muted)]">
                      <span>{patient.marketing_consent ? "يسمح بالتواصل التسويقي" : "لا يسمح بالتواصل التسويقي"}</span>
                      <span className="inline-flex items-center gap-1 font-bold text-teal-700">فتح الملف <ChevronLeft size={13} /></span>
                    </div>
                  </Link>
                ))}
              </div>

              <div className="table-shell hidden md:block">
                <table className="data-table min-w-[780px]">
                  <thead>
                    <tr>
                      <th>العميل</th>
                      <th>رقم الهاتف</th>
                      <th>مصدر العميل</th>
                      <th>الحالة</th>
                      <th>آخر تواصل</th>
                      <th>التواصل التسويقي</th>
                    </tr>
                  </thead>
                  <tbody>
                    {patients.map((patient) => (
                      <tr key={patient.id}>
                        <td className="font-bold">
                          <Link href={`/patients/${patient.id}`} className="text-teal-800 hover:underline">{patient.first_name} {patient.last_name || ""}</Link>
                        </td>
                        <td dir="ltr" className="text-right">{patient.phone || "—"}</td>
                        <td>{labelForSource(patient.source)}</td>
                        <td><Badge tone={toneForStatus(patient.status)}>{labelForStatus(patient.status)}</Badge></td>
                        <td>{formatDateTime(patient.last_contact_at)}</td>
                        <td>{patient.marketing_consent ? "مسموح" : "غير مسموح"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <EmptyState
              icon={UsersRound}
              title={q ? "لا يوجد عميل مطابق للبحث" : "لا يوجد عملاء بعد"}
              description={q ? "جرّب البحث بجزء من الاسم أو رقم الهاتف." : "سيظهر العملاء هنا بعد إضافتهم أو استيراد بيانات العيادة."}
            />
          )}
        </CardContent>
      </Card>
    </>
  );
}
