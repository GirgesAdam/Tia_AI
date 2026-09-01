import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Bot,
  CalendarCheck2,
  CalendarClock,
  CircleAlert,
  Clock3,
  ContactRound,
  CircleDollarSign,
  ListTodo,
  MessageSquareMore,
  Pin,
  StickyNote,
  Tag,
  UserRound,
} from "lucide-react";
import { addPatientNote, createPatientTask } from "../actions";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { appointmentLabels, labelForChannel, labelForPriority, labelForSource, labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { PatientProfile, PatientTimelineEvent } from "@/lib/types";

const noteLabels: Record<string, string> = {
  general: "ملاحظة عامة",
  preference: "تفضيل",
  customer_service: "خدمة عملاء",
  follow_up: "متابعة",
};

const handoffEventLabels: Record<string, string> = {
  created: "تم التصعيد للفريق",
  escalated: "تم رفع أولوية التصعيد",
  claimed: "استلم الفريق المتابعة",
  assigned: "تم إسناد المتابعة",
  staff_replied: "رد الفريق",
  resolved: "تم إنهاء المتابعة",
  reopened: "تم فتح المتابعة من جديد",
};

function actorLabel(event: PatientTimelineEvent) {
  if (event.actor_name) return event.actor_name;
  if (event.actor_type === "patient") return "العميل";
  if (event.actor_type === "ai") return "Tia";
  if (event.actor_type === "staff") return "الفريق";
  return "النظام";
}

function TimelineIcon({ event }: { event: PatientTimelineEvent }) {
  if (event.kind === "message") return event.actor_type === "ai" ? <Bot size={16} /> : <MessageSquareMore size={16} />;
  if (event.kind === "note") return <StickyNote size={16} />;
  if (event.kind === "appointment" || event.kind === "appointment_status") return <CalendarCheck2 size={16} />;
  if (event.kind === "handoff") return <CircleAlert size={16} />;
  if (event.kind === "task") return <ListTodo size={16} />;
  if (event.kind === "payment") return <CircleDollarSign size={16} />;
  return <ContactRound size={16} />;
}

function TimelineEvent({ event, patientId, isLast }: { event: PatientTimelineEvent; patientId: string; isLast: boolean }) {
  const appointment = event.appointment;
  const message = event.message;
  const handoff = event.handoff;
  const note = event.note;
  const task = event.task;
  const payment = event.payment;

  let title = "تم إنشاء ملف العميل";
  let body: ReactNode = null;

  if (note) {
    title = noteLabels[note.note_type] || "ملاحظة";
    body = <p className="whitespace-pre-wrap text-sm leading-6">{note.content}</p>;
  } else if (appointment && event.kind === "appointment") {
    title = `حجز ${appointment.service_name}`;
    body = (
      <div className="space-y-1 text-sm text-[var(--muted)]">
        <div>{formatDateTime(appointment.start_at)} · {appointment.branch_name} · {appointment.doctor_name}</div>
        <div>{formatMoney(appointment.price_minor, appointment.currency)}</div>
      </div>
    );
  } else if (appointment && event.kind === "appointment_status") {
    const from = appointment.from_status ? appointmentLabels[appointment.from_status] || appointment.from_status : "—";
    const to = appointment.to_status ? appointmentLabels[appointment.to_status] || appointment.to_status : appointment.status;
    title = `تغيير حالة الحجز: ${from} → ${to}`;
    body = (
      <div className="space-y-1 text-sm text-[var(--muted)]">
        <div>{appointment.service_name} · {formatDateTime(appointment.start_at)}</div>
        {appointment.reason && <div className="text-[var(--text)]">{appointment.reason}</div>}
      </div>
    );
  } else if (message) {
    title = message.sender_type === "patient" ? "رسالة من العميل" : message.sender_type === "ai" ? "رد Tia" : "رد الفريق";
    body = (
      <div className="space-y-2">
        <p className="whitespace-pre-wrap text-sm leading-6">{message.content || "رسالة بدون نص"}</p>
        <div className="flex flex-wrap gap-2 text-xs text-[var(--muted)]">
          <span>{labelForChannel(message.channel)}</span>
          <span>·</span>
          <span>{labelForStatus(message.delivery_status)}</span>
          <Link href={`/inbox/${message.conversation_id}`} className="font-bold text-teal-700">فتح المحادثة</Link>
        </div>
      </div>
    );
  } else if (task) {
    title = task.event_type === "completed" ? `تمت متابعة: ${task.title}` : `متابعة: ${task.title}`;
    body = (
      <div className="space-y-2 text-sm">
        <div className="text-[var(--muted)]">موعد المتابعة: {formatDateTime(task.due_at)}</div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={toneForStatus(task.priority)}>{labelForPriority(task.priority)}</Badge>
          <Badge tone={toneForStatus(task.status)}>{labelForStatus(task.status)}</Badge>
          <Link href={`/tasks?scope=all`} className="self-center text-xs font-bold text-teal-700">فتح المتابعات</Link>
        </div>
      </div>
    );
  } else if (handoff) {
    title = handoffEventLabels[handoff.event_type] || "تحديث متابعة الفريق";
    body = (
      <div className="space-y-2 text-sm">
        <p className="leading-6">{handoff.reason}</p>
        <div className="flex flex-wrap gap-2">
          <Badge tone={toneForStatus(handoff.priority)}>{labelForPriority(handoff.priority)}</Badge>
          <Link href={`/inbox/${handoff.conversation_id}`} className="self-center text-xs font-bold text-teal-700">فتح المحادثة</Link>
        </div>
      </div>
    );
  } else if (payment) {
    title = payment.transaction_type === "refund" ? "تم تسجيل استرداد" : "تم تسجيل دفعة";
    body = <div className="space-y-2 text-sm"><div className="text-lg font-black">{payment.transaction_type === "refund" ? "−" : "+"}{formatMoney(payment.amount_minor,payment.currency)}</div><div className="text-[var(--muted)]">{({cash:"نقدي",card:"بطاقة",bank_transfer:"تحويل بنكي",wallet:"محفظة إلكترونية",online:"دفع إلكتروني",other:"أخرى"} as Record<string,string>)[payment.payment_method] || "طريقة دفع غير محددة"}</div>{payment.reason && <div>{payment.reason}</div>}{payment.appointment_id ? <Link href={`/appointments/${payment.appointment_id}`} className="text-xs font-bold text-teal-700">فتح الموعد</Link> : <div className="text-xs text-[var(--muted)]">دفعة عامة مسجلة على حساب العميل</div>}</div>;
  }

  return (
    <div className="relative flex gap-4 pb-7 last:pb-0">
      {!isLast && <div className="absolute bottom-0 right-[17px] top-9 w-px bg-[var(--border)]" />}
      <div className="relative z-10 grid size-9 shrink-0 place-items-center rounded-full border border-[var(--border)] bg-white text-teal-700">
        <TimelineIcon event={event} />
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div className="font-bold">{title}</div>
            {note?.is_pinned && <Pin size={13} className="text-amber-600" />}
            {appointment && <Badge tone={toneForStatus(appointment.to_status || appointment.status)}>{appointmentLabels[appointment.to_status || appointment.status] || appointment.to_status || appointment.status}</Badge>}
          </div>
          <div className="text-xs text-[var(--muted)]">{formatDateTime(event.occurred_at)}</div>
        </div>
        <div className="mt-1 text-xs text-[var(--muted)]">بواسطة {actorLabel(event)}</div>
        {body && <div className="mt-3 rounded-xl bg-[var(--surface-2)] p-3">{body}</div>}
        {event.kind === "appointment" && (
          <Link href={`/appointments?patient_id=${patientId}`} className="mt-2 inline-block text-xs font-bold text-teal-700">عرض حجوزات العميل</Link>
        )}
      </div>
    </div>
  );
}

function languageLabel(value: string | null | undefined) {
  if (!value) return "غير محددة";
  const normalized = value.toLowerCase();
  if (normalized.startsWith("ar")) return "العربية";
  if (normalized.startsWith("en")) return "الإنجليزية";
  return "لغة أخرى";
}

export default async function PatientProfilePage({ params }: { params: Promise<{ patientId: string }> }) {
  const { patientId } = await params;
  const [profile, ctx] = await Promise.all([
    tiaRequest<PatientProfile>(`/crm/patients/${patientId}/profile?timeline_limit=75`),
    getAppContext(),
  ]);
  const { patient, stats } = profile;
  const patientName = `${patient.first_name} ${patient.last_name || ""}`.trim();

  return (
    <>
      <PageHeader
        title={patientName}
        description={patient.phone || "ملف العميل"}
        action={
          <div className="flex flex-wrap gap-2">
            {profile.latest_conversation_id && (
              <Link href={`/inbox/${profile.latest_conversation_id}`} className={buttonVariants()}>
                <MessageSquareMore size={15} /> فتح المحادثة
              </Link>
            )}
            <Link href="/patients" className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft size={15} /> العملاء
            </Link>
          </div>
        }
      />

      <div className="mb-5 flex flex-wrap gap-2">
        <Badge tone={toneForStatus(patient.status)}>{labelForStatus(patient.status)}</Badge>
        <Badge>{labelForSource(patient.source)}</Badge>
        {patient.marketing_consent && <Badge tone="green">موافق على الرسائل التسويقية</Badge>}
        {profile.tags.map((tag) => <Badge key={tag.id} tone="purple"><Tag size={11} className="ml-1" />{tag.name}</Badge>)}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="الحجوزات" value={stats.total_appointments} detail={`${stats.completed_appointments} مكتملة · ${stats.no_show_appointments} عدم حضور`} icon={CalendarCheck2} />
        <StatCard label="الموعد القادم" value={stats.upcoming_appointments} detail={stats.next_appointment_at ? formatDateTime(stats.next_appointment_at) : "لا يوجد موعد قادم"} icon={CalendarClock} />
        <StatCard label="المحادثات" value={stats.total_conversations} detail={stats.open_conversations ? `${stats.open_conversations} مفتوحة حاليًا` : "لا توجد محادثات مفتوحة"} icon={MessageSquareMore} />
        <StatCard label="متابعات مفتوحة" value={stats.active_handoffs + stats.open_tasks} detail={stats.overdue_tasks ? `${stats.overdue_tasks} متأخرة` : "لا توجد متابعات متأخرة"} icon={ListTodo} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.45fr_.75fr]">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>سجل العميل</CardTitle>
              <p className="mt-1 text-xs text-[var(--muted)]">المواعيد والمحادثات والمتابعات والمدفوعات والملاحظات في ترتيب زمني واحد.</p>
            </div>
            <Clock3 size={18} className="text-[var(--muted)]" />
          </CardHeader>
          <CardContent>
            {profile.timeline.length ? (
              <div>{profile.timeline.map((event, index) => <TimelineEvent key={event.id} event={event} patientId={patient.id} isLast={index === profile.timeline.length - 1} />)}</div>
            ) : (
              <div className="py-12 text-center text-sm text-[var(--muted)]">لا يوجد نشاط مسجل حتى الآن.</div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>بيانات العميل</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex justify-between gap-4"><span className="text-[var(--muted)]">رقم الهاتف</span><b className="text-left" dir="ltr">{patient.phone || "—"}</b></div>
              <div className="flex justify-between gap-4"><span className="text-[var(--muted)]">اللغة المفضلة</span><b>{languageLabel(patient.preferred_language)}</b></div>
              <div className="flex justify-between gap-4"><span className="text-[var(--muted)]">تاريخ الميلاد</span><b>{formatDate(patient.birth_date)}</b></div>
              <div className="flex justify-between gap-4"><span className="text-[var(--muted)]">مصدر العميل</span><b>{labelForSource(patient.source)}</b></div>
              <div className="flex justify-between gap-4"><span className="text-[var(--muted)]">آخر تواصل</span><b className="text-left">{formatDateTime(patient.last_contact_at)}</b></div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>إجراءات سريعة</CardTitle>
              <p className="text-xs leading-5 text-[var(--muted)]">أضف متابعة أو ملاحظة عند الحاجة بدون ازدحام الصفحة بنماذج مفتوحة.</p>
            </CardHeader>
            <CardContent className="space-y-3">
              <details className="rounded-xl border border-[var(--border)] p-3">
                <summary className="cursor-pointer text-sm font-bold text-slate-800">جدولة متابعة</summary>
                <form action={createPatientTask} className="mt-4 space-y-3">
                  <input type="hidden" name="patient_id" value={patient.id} />
                  <input type="hidden" name="assigned_user_id" value={ctx.me.user.id} />
                  <input type="hidden" name="conversation_id" value={profile.latest_conversation_id || ""} />
                  <Input name="title" required maxLength={200} placeholder="مثال: التواصل بعد الاستشارة" />
                  <Input name="due_at" type="datetime-local" required />
                  <select name="execution_mode" defaultValue="ai" className="form-control h-10 min-h-10">
                    <option value="ai">Tia ترسل المتابعة تلقائيًا</option>
                    <option value="human">متابعة يدوية للفريق</option>
                  </select>
                  <select name="priority" defaultValue="normal" className="form-control h-10 min-h-10">
                    <option value="low">أولوية منخفضة</option>
                    <option value="normal">أولوية عادية</option>
                    <option value="high">أولوية مرتفعة</option>
                    <option value="urgent">أولوية عاجلة</option>
                  </select>
                  <Textarea name="description" maxLength={5000} placeholder="تفاصيل تساعد على تنفيذ المتابعة بشكل مناسب..." />
                  <Button className="w-full"><ListTodo size={15} /> حفظ المتابعة</Button>
                </form>
              </details>

              <details className="rounded-xl border border-[var(--border)] p-3">
                <summary className="cursor-pointer text-sm font-bold text-slate-800">إضافة ملاحظة</summary>
                <form action={addPatientNote} className="mt-4 space-y-3">
                  <input type="hidden" name="patient_id" value={patient.id} />
                  <select name="note_type" defaultValue="general" className="form-control h-10 min-h-10">
                    <option value="general">ملاحظة عامة</option>
                    <option value="preference">تفضيل</option>
                    <option value="customer_service">خدمة عملاء</option>
                    <option value="follow_up">متابعة</option>
                  </select>
                  <Textarea name="content" required placeholder="اكتب المعلومة المهمة للفريق..." />
                  <label className="flex items-center gap-2 text-xs text-[var(--muted)]">
                    <input type="checkbox" name="is_pinned" />
                    تثبيت الملاحظة ضمن الملاحظات المهمة
                  </label>
                  <Button variant="secondary" className="w-full"><StickyNote size={15} /> حفظ الملاحظة</Button>
                </form>
              </details>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>الملاحظات المهمة</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {profile.notes.length ? profile.notes.slice(0, 5).map((note) => (
                <div key={note.id} className="rounded-xl border border-[var(--border)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Badge>{noteLabels[note.note_type] || "ملاحظة"}</Badge>
                    <div className="flex items-center gap-1 text-[11px] text-[var(--muted)]">{note.is_pinned && <Pin size={11} />} {formatDateTime(note.created_at)}</div>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{note.content}</p>
                </div>
              )) : <div className="text-sm text-[var(--muted)]">لا توجد ملاحظات مسجلة.</div>}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
