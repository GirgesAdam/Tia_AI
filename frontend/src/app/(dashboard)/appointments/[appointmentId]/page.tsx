import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  CircleX,
  History,
  PackagePlus,
  ReceiptText,
  Stethoscope,
  Trash2,
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
import type { AppointmentOperationsDetail, AppointmentPaymentSummary, Doctor, Staff } from "@/lib/types";
import {
  addAppointmentProduct,
  cancelAppointment,
  confirmAppointment,
  recordAppointmentPayment,
  refundAppointmentPayment,
  removeAppointmentProduct,
  updateAppointmentStatus,
} from "./actions";
import {
  AppointmentServiceEditor,
  type AppointmentDevicePrice,
  type AppointmentServiceOption,
} from "./service-editor";

const paymentMethodLabels: Record<string, string> = {
  cash: "Cash",
  visa: "Visa",
  instapay: "InstaPay",
  card: "بطاقة - سجل قديم",
  bank_transfer: "تحويل بنكي - سجل قديم",
  wallet: "محفظة إلكترونية - سجل قديم",
  online: "دفع إلكتروني - سجل قديم",
  other: "طريقة قديمة أخرى",
  unknown: "غير محدد",
};

type ClinicProduct = {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
};

type AppointmentProductLine = {
  id: string;
  appointment_id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price_minor: number;
  currency: string;
  total_minor: number;
};

type PaymentSummaryWithProducts = AppointmentPaymentSummary & {
  service_price_minor?: number;
  products_total_minor?: number;
};

function minorInput(value: number) {
  return (value / 100).toFixed(2);
}

export default async function AppointmentOperationsPage({ params }: { params: Promise<{ appointmentId: string }> }) {
  const { appointmentId } = await params;
  const [detail, payments, products, productLines, services, devicePrices, doctors, staff] = await Promise.all([
    tiaRequest<AppointmentOperationsDetail>(`/booking/appointments/${appointmentId}/operations`),
    tiaRequest<PaymentSummaryWithProducts>(`/payments/appointments/${appointmentId}`),
    tiaRequest<ClinicProduct[]>("/inventory/products").catch(() => []),
    tiaRequest<AppointmentProductLine[]>(`/inventory/appointments/${appointmentId}/products`).catch(() => []),
    tiaRequest<AppointmentServiceOption[]>("/clinic/services").catch(() => []),
    tiaRequest<AppointmentDevicePrice[]>("/inventory/laser-prices").catch(() => []),
    tiaRequest<Doctor[]>("/clinic/doctors").catch(() => []),
    tiaRequest<Staff[]>("/clinic/staff").catch(() => []),
  ]);
  const { appointment } = detail;
  const allowed = new Set(detail.allowed_actions);
  const laserAppointment = appointment as typeof appointment & {
    laser_device_key?: string | null;
    laser_device_name?: string | null;
  };
  const canAddProducts = !["cancelled", "no_show", "rescheduled"].includes(appointment.status);
  const canEditService = ["pending", "confirmed", "checked_in", "in_progress"].includes(appointment.status);
  const packageBacked = Boolean(
    appointment.patient_package_id || appointment.billing_context === "package_prepaid" || appointment.package_external_id,
  );
  const overpaidMinor = Math.max(payments.net_paid_minor - payments.price_minor, 0);
  const staffMap = new Map(staff.map((item) => [item.id, `${item.first_name} ${item.last_name}`.trim()]));
  const doctorOptions = doctors
    .filter((item) => item.is_active)
    .map((item) => ({ id: item.id, name: staffMap.get(item.staff_id) || "دكتور" }));

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
              <div className="grid gap-3 sm:grid-cols-3">
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
                  <div className="mt-1 text-xs text-[var(--muted)]">{detail.doctor.name} · {formatMoney(payments.service_price_minor ?? appointment.price_minor, appointment.currency)}</div>
                  {laserAppointment.laser_device_name && <div className="mt-1 text-xs font-bold text-teal-700">الجهاز: {laserAppointment.laser_device_name}</div>}
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

              {canEditService && services.length > 0 && (
                <AppointmentServiceEditor
                  appointmentId={appointment.id}
                  patientId={appointment.patient_id}
                  currentServiceId={appointment.service_id}
                  currentDoctorId={appointment.doctor_id}
                  currentDeviceKey={laserAppointment.laser_device_key || null}
                  packageBacked={packageBacked}
                  services={services}
                  doctors={doctorOptions}
                  devicePrices={devicePrices}
                />
              )}

              {allowed.has("cancel") && (
                <details className="mt-4 rounded-xl border border-red-100 bg-red-50/40 p-3">
                  <summary className="cursor-pointer text-sm font-bold text-red-700">إلغاء الموعد</summary>
                  <div className="mt-3">
                    {detail.cancellation_override_required && !detail.can_override_cancellation_policy ? (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">الموعد داخل مهلة منع الإلغاء، لذلك يحتاج مدير العيادة إلى تنفيذ الإلغاء.</div>
                    ) : (
                      <form action={cancelAppointment} className="space-y-3">
                        <input type="hidden" name="appointment_id" value={appointment.id} />
                        <input type="hidden" name="patient_id" value={appointment.patient_id} />
                        <label className="block text-sm font-bold">سبب الإلغاء<input name="reason" required maxLength={2000} placeholder="مثال: طلب العميل إلغاء الموعد" className="form-control mt-2 h-10 min-h-10" /></label>
                        {detail.cancellation_override_required && <label className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm"><input type="checkbox" name="override_policy" value="1" required className="mt-1" />تأكيد الإلغاء رغم تجاوز مهلة الإلغاء المسموح بها</label>}
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
                {payments.balance_minor > 0 && payments.billing_context !== "package_prepaid" && <Badge tone="yellow">متبقي {formatMoney(payments.balance_minor, payments.currency)}</Badge>}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">قيمة الخدمة</div><b className="mt-1 block">{formatMoney(payments.service_price_minor ?? appointment.price_minor, payments.currency)}</b></div>
                <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">المنتجات</div><b className="mt-1 block">{formatMoney(payments.products_total_minor ?? 0, payments.currency)}</b></div>
                <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">الإجمالي المستحق</div><b className="mt-1 block">{formatMoney(payments.price_minor, payments.currency)}</b></div>
              </div>

              {overpaidMinor > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
                  المدفوع المسجل أعلى من الإجمالي الحالي بمقدار {formatMoney(overpaidMinor, payments.currency)}. راجع الاسترداد المناسب بدل حذف أي دفعة قديمة.
                </div>
              )}

              <details className="rounded-xl border border-slate-200 p-3" open={productLines.length > 0 ? true : undefined}>
                <summary className="flex cursor-pointer items-center gap-2 text-sm font-black text-slate-900"><PackagePlus size={16} /> إضافة منتج</summary>
                <div className="mt-4 space-y-3">
                  {productLines.length > 0 && (
                    <div className="space-y-2">
                      {productLines.map((line) => (
                        <div key={line.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-3">
                          <div><div className="text-sm font-black">{line.product_name}</div><div className="mt-1 text-xs text-[var(--muted)]">{line.quantity} × {formatMoney(line.unit_price_minor, line.currency)}</div></div>
                          <div className="flex items-center gap-2"><b>{formatMoney(line.total_minor, line.currency)}</b><form action={removeAppointmentProduct}><input type="hidden" name="appointment_id" value={appointment.id} /><input type="hidden" name="patient_id" value={appointment.patient_id} /><input type="hidden" name="line_id" value={line.id} /><Button size="sm" variant="ghost" aria-label={`حذف ${line.product_name}`}><Trash2 size={14} /></Button></form></div>
                        </div>
                      ))}
                    </div>
                  )}
                  {canAddProducts && products.length > 0 ? (
                    <form action={addAppointmentProduct} className="grid gap-3 md:grid-cols-[minmax(180px,1fr)_110px_160px_auto] md:items-end">
                      <input type="hidden" name="appointment_id" value={appointment.id} />
                      <input type="hidden" name="patient_id" value={appointment.patient_id} />
                      <label className="text-xs font-bold">المنتج<select name="product_id" required defaultValue="" className="form-control mt-1.5 h-10 min-h-10"><option value="" disabled>اختار المنتج</option>{products.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                      <label className="text-xs font-bold">الكمية<input name="quantity" type="number" min="1" max="100" defaultValue="1" required className="form-control mt-1.5 h-10 min-h-10" /></label>
                      <label className="text-xs font-bold">سعر القطعة<input name="unit_price" inputMode="decimal" required placeholder="0.00" className="form-control mt-1.5 h-10 min-h-10" /></label>
                      <Button><PackagePlus size={14} /> إضافة</Button>
                    </form>
                  ) : canAddProducts ? <div className="text-xs text-[var(--muted)]">أضف منتجات العيادة من صفحة المخزن أولًا.</div> : null}
                </div>
              </details>

              {payments.billing_context === "package_prepaid" ? (
                <div className="rounded-xl border border-teal-200 bg-teal-50 p-3 text-sm text-teal-900">الجلسة نفسها ضمن باقة مدفوعة مسبقًا. أي منتجات مضافة تظهر كمبلغ إضافي مستقل إذا وُجدت.</div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">صافي المدفوع</div><b className="mt-1 block">{formatMoney(payments.net_paid_minor, payments.currency)}</b></div>
                  <div className="rounded-xl bg-[var(--surface-2)] p-3"><div className="text-xs text-[var(--muted)]">المتبقي</div><b className="mt-1 block">{formatMoney(payments.balance_minor, payments.currency)}</b></div>
                </div>
              )}

              {payments.refunded_minor > 0 && <div className="text-xs text-[var(--muted)]">تم استرداد {formatMoney(payments.refunded_minor, payments.currency)} من المدفوعات المسجلة.</div>}

              {payments.balance_minor > 0 && ["pending", "confirmed", "completed"].includes(appointment.status) && (
                <form action={recordAppointmentPayment} className="grid gap-3 rounded-xl border border-[var(--border)] p-4 md:grid-cols-2">
                  <input type="hidden" name="appointment_id" value={appointment.id} />
                  <input type="hidden" name="patient_id" value={appointment.patient_id} />
                  <label className="text-sm font-bold">المبلغ ({payments.currency})<input name="amount" inputMode="decimal" required defaultValue={minorInput(payments.balance_minor)} className="form-control mt-2 h-10 min-h-10" /></label>
                  <label className="text-sm font-bold">طريقة الدفع<select name="payment_method" defaultValue="cash" className="form-control mt-2 h-10 min-h-10"><option value="cash">Cash</option><option value="visa">Visa</option><option value="instapay">InstaPay</option></select></label>
                  <label className="text-sm font-bold md:col-span-2">رقم الإيصال أو المرجع - اختياري<input name="external_reference" maxLength={128} placeholder="مثال: رقم الإيصال" className="form-control mt-2 h-10 min-h-10" /></label>
                  <div className="md:col-span-2"><Button><CircleDollarSign size={15} /> تسجيل الدفعة</Button></div>
                </form>
              )}

              {payments.transactions.length > 0 && (
                <details className="rounded-xl border border-[var(--border)] p-3">
                  <summary className="cursor-pointer text-sm font-bold text-slate-800">سجل المدفوعات والاستردادات</summary>
                  <div className="mt-4 space-y-3">
                    {payments.transactions.slice().reverse().map((transaction) => (
                      <div key={transaction.id} className="rounded-xl bg-[var(--surface-2)] p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><ReceiptText size={15} /><b>{transaction.transaction_type === "refund" ? "استرداد" : "دفعة"}</b><Badge tone={transaction.transaction_type === "refund" ? "yellow" : "green"}>{formatMoney(transaction.allocated_amount_minor ?? transaction.amount_minor, transaction.currency)}</Badge></div><span className="text-xs text-[var(--muted)]">{formatDateTime(transaction.created_at)}</span></div>
                        <div className="mt-2 text-xs text-[var(--muted)]">{paymentMethodLabels[transaction.payment_method] || "غير محدد"}{transaction.external_reference ? ` · مرجع ${transaction.external_reference}` : ""}</div>
                        {transaction.reason && <div className="mt-2 text-sm">{transaction.reason}</div>}
                        {payments.can_refund && transaction.transaction_type === "payment" && transaction.refundable_minor > 0 && (
                          <details className="mt-3 rounded-lg border border-red-100 bg-white p-3"><summary className="cursor-pointer text-xs font-bold text-red-700">استرداد من هذه الدفعة</summary><form action={refundAppointmentPayment} className="mt-3 grid gap-2 sm:grid-cols-[140px_1fr_auto]"><input type="hidden" name="appointment_id" value={appointment.id} /><input type="hidden" name="patient_id" value={appointment.patient_id} /><input type="hidden" name="payment_transaction_id" value={transaction.id} /><input name="amount" inputMode="decimal" required defaultValue={minorInput(transaction.refundable_minor)} className="form-control h-9 min-h-9 px-2 text-sm" aria-label="قيمة الاسترداد" /><input name="reason" required maxLength={500} placeholder="سبب الاسترداد" className="form-control h-9 min-h-9 px-2 text-sm" /><Button variant="danger" size="sm">استرداد</Button></form></details>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {!payments.transactions.length && <div className="text-sm text-[var(--muted)]">لا توجد دفعات مسجلة لهذا الموعد حتى الآن.</div>}
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
                  {detail.automations.map((job) => <div key={job.id} className="rounded-xl bg-[var(--surface-2)] p-3"><div className="flex items-center justify-between gap-2"><b className="text-sm">رسالة تلقائية</b><Badge tone={toneForStatus(job.status)}>{labelForStatus(job.status)}</Badge></div><div className="mt-1 text-xs text-[var(--muted)]">{formatDateTime(job.scheduled_for)}</div>{job.last_error && <div className="mt-2 text-xs font-semibold text-red-700">لم تكتمل الرسالة تلقائيًا. يمكن مراجعتها من صفحة Automation.</div>}</div>)}
                  {!detail.automations.length && <div className="text-sm text-[var(--muted)]">لا توجد رسائل تلقائية مرتبطة بهذا الموعد.</div>}
                </div>
              </details>

              <details className="rounded-xl border border-[var(--border)] p-3">
                <summary className="flex cursor-pointer items-center gap-2 text-sm font-bold text-slate-800"><History size={15} /> سجل تغييرات الحالة</summary>
                <div className="mt-3 space-y-3">
                  {detail.history.map((item) => <div key={item.id} className="border-r-2 border-teal-200 pr-3"><div className="flex flex-wrap items-center gap-2"><Badge tone={toneForStatus(item.to_status)}>{appointmentLabels[item.to_status] || "تم تحديث الحالة"}</Badge>{item.from_status && <span className="text-xs text-[var(--muted)]">بعد {appointmentLabels[item.from_status] || "الحالة السابقة"}</span>}</div><div className="mt-1 text-xs text-[var(--muted)]">{formatDateTime(item.created_at)}</div>{item.reason && <div className="mt-1 text-sm">{item.reason}</div>}</div>)}
                </div>
              </details>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
