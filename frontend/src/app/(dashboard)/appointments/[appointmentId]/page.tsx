import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  CircleX,
  History,
  MapPin,
  ReceiptText,
  Stethoscope,
  UserRound,
  UserX,
  Workflow,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime, formatMoney } from "@/lib/format";
import { appointmentLabels, labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import type { AppointmentOperationsDetail, AppointmentPaymentSummary } from "@/lib/types";
import {
  cancelAppointment,
  confirmAppointment,
  recordAppointmentPayment,
  refundAppointmentPayment,
  updateAppointmentStatus,
} from "./actions";

const paymentMethodLabels: Record<string, string> = {
  cash: "نقدي",
  card: "بطاقة",
  bank_transfer: "تحويل بنكي",
  wallet: "محفظة إلكترونية",
  online: "دفع إلكتروني",
  other: "أخرى",
  unknown: "غير محدد",
};

function minorInput(value: number) {
  return (value / 100).toFixed(2);
}

export default async function AppointmentOperationsPage({ params }: { params: Promise<{ appointmentId: string }> }) {
  const { appointmentId } = await params;
  const [detail, payments] = await Promise.all([
    tiaRequest<AppointmentOperationsDetail>(`/booking/appointments/${appointmentId}/operations`),
    tiaRequest<AppointmentPaymentSummary>(`/payments/appointments/${appointmentId}`),
  ]);
  const { appointment } = detail;
  const allowed = new Set(detail.allowed_actions);

  return (
    <>
      <PageHeader
        title={detail.patient.name}
        description={`${detail.service.name} · ${formatDateTime(appointment.start_at)}`}
        action={
          <Link href="/appointments" className={buttonVariants({ variant: "outline" })}>
            <ArrowRight size={15} /> المواعيد
          </Link>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-5">
          <Card>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div>
                <CardTitle>تفاصيل الموعد</CardTitle>
                <div className="mt-1 text-xs text-[var(--muted)]">أهم بيانات الموعد والإجراء المناسب لحالته الحالية.</div>
              </div>
              <Badge tone={toneForStatus(appointment.status)}>{appointmentLabels[appointment.status] || "غير محدد"}</Badge>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-[var(--surface-2)] p-4">
                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]"><UserRound size={14} /> العميل</div>
                  <Link href={`/patients/${detail.patient.id}`} className="mt-1 block font-black text-teal-800 hover:underline">{detail.patient.name}</Link>
                  <div className="mt-1 text-xs text-[var(--muted)]" dir="ltr">{detail.patient.phone || "—"}</div>
                </div>
                <div className="rounded-xl bg-[var(--surface-2)] p-4">
                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]"><CalendarClock size={14} /> الموعد</div>
                  <div className="mt-1 font-black">{formatDateTime(appointment.start_at)}</div>
                  <div className="mt-1 text-xs text-[var(--muted)]">{appointment.duration_minutes} دقيقة</div>
                </div>
                <div className="rounded-xl bg-[var(--surface-2)] p-4">
                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]"><Stethoscope size={14} /> الخدمة والطبيب</div>
                  <div className="mt-1 font-black">{detail.service.name}</div>
                  <div className="mt-1 text-xs text-[var(--muted)]">{detail.doctor.name}</div>
                </div>
                <div className="rounded-xl bg-[var(--surface-2)] p-4">
                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]"><MapPin size={14} /> الفرع</div>
                  <div className="mt-1 font-black">{detail.branch.name}</div>
                  <div className="mt-1 text-xs text-[var(--muted)]">{formatMoney(appointment.price_minor, appointment.currency)}</div>
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-2 border-t border-[var(--border)] pt-4">
                {allowed.has("confirm") && (
                  <form action={confirmAppointment}>
                    <input type="hidden" name="appointment_id" value={appointment.id} />
                    <input type="hidden" name="patient_id" value={appointment.patient_id} />
                    <Button><CheckCircle2 size={15} /> تأكيد الموعد</Button>
                  </form>
                )}
                {allowed.has("complete") && (
                  <form action={updateAppointmentStatus}>
                    <input type="hidden" name="appointment_id" value={appointment.id} />
                    <input type="hidden" name="patient_id" value={appointment.patient_id} />
                    <input type="hidden" name="status" value="completed" />
                    <Button><CheckCircle2 size={15} /> تسجيل اكتمال الجلسة</Button>
                  </form>
                )}
                {allowed.has("reschedule") && (
                  <Link href={`/appointments/${appointment.id}/reschedule`} className={buttonVariants({ variant: "outline" })}>
                    <CalendarClock size={15} /> تغيير الموعد
                  </Link>
                )}
                {allowed.has("no_show") && (
                  <form action={updateAppointmentStatus}>
                    <input type="hidden" name="appointment_id" value={appointment.id} />
                    <input type="hidden" name="patient_id" value={appointment.patient_id} />
                    <input type="hidden" name="status" value="no_show" />
                    <Button variant="ghost"><UserX size={15} /> تسجيل عدم الحضور</Button>
                  </form>
                )}
              </div>

              {allowed.has("cancel") && (
                <details className="mt-4 rounded-xl border border-red-100 bg-red-50/40 p-3">
                  <summary className="cursor-pointer text-sm font-bold text-red-700">إلغاء الموعد</summary>
                  <div className="mt-3">
                    {detail.cancellation_override_required && !detail.can_override_cancellation_policy ? (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                        الموعد داخل مهلة منع الإلغاء، لذلك يحتاج مدير العيادة إلى تنفيذ الإلغاء.
                      </div>
                    ) : (
                      <form action={cancelAppointment} className="space-y-3">
                        <input type="hidden" name="appointment_id" value={appointment.id} />
                        <input type="hidden" name="patient_id" value={appointment.patient_id} />
                        <label className="block text-sm font-bold">
                          سبب الإلغاء
                          <input name="reason" required maxLength={2000} placeholder="مثال: طلب العميل إلغاء الموعد" className="form-control mt-2 h-10 min-h-10" />
                        </label>
                        {detail.cancellation_override_required && (
                          <label className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm">
                            <input type="checkbox" name="override_policy" value="1" required className="mt-1" />
                            تأكيد الإلغاء رغم تجاوز مهلة الإلغاء المسموح بها
                          </label>
                        )}
                        <Button variant="danger"><CircleX size={15} /> تأكيد الإلغاء</Button>
                      </form>
                    )}
                  </div>
                </details>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2"><CircleDollarSign size={17} /> المدفوعات</CardTitle>
                {payments.balance_minor > 0 && payments.billing_context !== "package_prepaid" && (
                  <Badge tone="yellow">متبقي {formatMoney(payments.balance_minor, payments.currency)}</Badge>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {payments.billing_context === "package_prepaid" ? (
                <div className="rounded-xl border border-teal-200 bg-teal-50 p-3 text-sm text-teal-900">
                  هذه الجلسة محسوبة ضمن باقة مدفوعة مسبقًا، ولا يوجد مبلغ إضافي مستحق على الجلسة نفسها.
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">قيمة الموعد</div><b className="mt-1 block">{formatMoney(appointment.price_minor, appointment.currency)}</b></div>
                  <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">صافي المدفوع</div><b className="mt-1 block">{formatMoney(payments.net_paid_minor, payments.currency)}</b></div>
                  <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">المتبقي</div><b className="mt-1 block">{formatMoney(payments.balance_minor, payments.currency)}</b></div>
                </div>
              )}

              {payments.refunded_minor > 0 && (
                <div className="text-xs text-[var(--muted)]">تم استرداد {formatMoney(payments.refunded_minor, payments.currency)} من المدفوعات المسجلة.</div>
              )}

              {payments.balance_minor > 0 && ["pending", "confirmed", "completed"].includes(appointment.status) && payments.billing_context !== "package_prepaid" && (
                <form action={recordAppointmentPayment} className="grid gap-3 rounded-xl border border-[var(--border)] p-4 md:grid-cols-2">
                  <input type="hidden" name="appointment_id" value={appointment.id} />
                  <input type="hidden" name="patient_id" value={appointment.patient_id} />
                  <label className="text-sm font-bold">
                    المبلغ ({payments.currency})
                    <input name="amount" inputMode="decimal" required defaultValue={minorInput(payments.balance_minor)} className="form-control mt-2 h-10 min-h-10" />
                  </label>
                  <label className="text-sm font-bold">
                    طريقة الدفع
                    <select name="payment_method" defaultValue="cash" className="form-control mt-2 h-10 min-h-10">
                      <option value="cash">نقدي</option>
                      <option value="card">بطاقة</option>
                      <option value="bank_transfer">تحويل بنكي</option>
                      <option value="wallet">محفظة إلكترونية</option>
                      <option value="online">دفع إلكتروني</option>
                      <option value="other">أخرى</option>
                    </select>
                  </label>
                  <label className="text-sm font-bold md:col-span-2">
                    رقم الإيصال أو المرجع - اختياري
                    <input name="external_reference" maxLength={128} placeholder="مثال: رقم الإيصال" className="form-control mt-2 h-10 min-h-10" />
                  </label>
                  <div className="md:col-span-2"><Button><CircleDollarSign size={15} /> تسجيل الدفعة</Button></div>
                </form>
              )}

              {payments.transactions.length > 0 && (
                <details className="rounded-xl border border-[var(--border)] p-3">
                  <summary className="cursor-pointer text-sm font-bold text-slate-800">سجل المدفوعات والاستردادات</summary>
                  <div className="mt-4 space-y-3">
                    {payments.transactions.slice().reverse().map((transaction) => (
                      <div key={transaction.id} className="rounded-xl bg-[var(--surface-2)] p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <ReceiptText size={15} />
                            <b>{transaction.transaction_type === "refund" ? "استرداد" : "دفعة"}</b>
                            <Badge tone={transaction.transaction_type === "refund" ? "yellow" : "green"}>
                              {formatMoney(transaction.allocated_amount_minor ?? transaction.amount_minor, transaction.currency)}
                            </Badge>
                          </div>
                          <span className="text-xs text-[var(--muted)]">{formatDateTime(transaction.created_at)}</span>
                        </div>
                        <div className="mt-2 text-xs text-[var(--muted)]">
                          {paymentMethodLabels[transaction.payment_method] || "غير محدد"}
                          {transaction.external_reference ? ` · مرجع ${transaction.external_reference}` : ""}
                        </div>
                        {transaction.reason && <div className="mt-2 text-sm">{transaction.reason}</div>}
                        {payments.can_refund && transaction.transaction_type === "payment" && transaction.refundable_minor > 0 && (
                          <details className="mt-3 rounded-lg border border-red-100 bg-white p-3">
                            <summary className="cursor-pointer text-xs font-bold text-red-700">استرداد من هذه الدفعة</summary>
                            <form action={refundAppointmentPayment} className="mt-3 grid gap-2 sm:grid-cols-[140px_1fr_auto]">
                              <input type="hidden" name="appointment_id" value={appointment.id} />
                              <input type="hidden" name="patient_id" value={appointment.patient_id} />
                              <input type="hidden" name="payment_transaction_id" value={transaction.id} />
                              <input name="amount" inputMode="decimal" required defaultValue={minorInput(transaction.refundable_minor)} className="form-control h-9 min-h-9 px-2 text-sm" aria-label="قيمة الاسترداد" />
                              <input name="reason" required maxLength={500} placeholder="سبب الاسترداد" className="form-control h-9 min-h-9 px-2 text-sm" />
                              <Button variant="danger" size="sm">استرداد</Button>
                            </form>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {!payments.transactions.length && (
                <div className="text-sm text-[var(--muted)]">
                  {payments.billing_context === "package_prepaid" ? "المدفوعات مسجلة على الباقة وليس على هذه الجلسة." : "لا توجد دفعات مسجلة لهذا الموعد حتى الآن."}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>متابعة الموعد</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <details className="rounded-xl border border-[var(--border)] p-3">
                <summary className="flex cursor-pointer items-center gap-2 text-sm font-bold text-slate-800"><Workflow size={15} /> الرسائل التلقائية</summary>
                <div className="mt-3 space-y-3">
                  {detail.automations.map((job) => (
                    <div key={job.id} className="rounded-xl bg-[var(--surface-2)] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <b className="text-sm">رسالة تلقائية</b>
                        <Badge tone={toneForStatus(job.status)}>{labelForStatus(job.status)}</Badge>
                      </div>
                      <div className="mt-1 text-xs text-[var(--muted)]">{formatDateTime(job.scheduled_for)}</div>
                      {job.last_error && <div className="mt-2 text-xs font-semibold text-red-700">لم تكتمل الرسالة تلقائيًا. يمكن مراجعتها من صفحة الأتمتة.</div>}
                    </div>
                  ))}
                  {!detail.automations.length && <div className="text-sm text-[var(--muted)]">لا توجد رسائل تلقائية مرتبطة بهذا الموعد.</div>}
                </div>
              </details>

              <details className="rounded-xl border border-[var(--border)] p-3">
                <summary className="flex cursor-pointer items-center gap-2 text-sm font-bold text-slate-800"><History size={15} /> سجل تغييرات الحالة</summary>
                <div className="mt-3 space-y-3">
                  {detail.history.map((item) => (
                    <div key={item.id} className="border-r-2 border-teal-200 pr-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={toneForStatus(item.to_status)}>{appointmentLabels[item.to_status] || "تم تحديث الحالة"}</Badge>
                        {item.from_status && <span className="text-xs text-[var(--muted)]">بعد {appointmentLabels[item.from_status] || "الحالة السابقة"}</span>}
                      </div>
                      <div className="mt-1 text-xs text-[var(--muted)]">{formatDateTime(item.created_at)}</div>
                      {item.reason && <div className="mt-1 text-sm">{item.reason}</div>}
                    </div>
                  ))}
                </div>
              </details>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
