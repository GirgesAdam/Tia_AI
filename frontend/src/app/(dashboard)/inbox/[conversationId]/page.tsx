import Link from "next/link";
import { ArrowRight, Bot, CheckCircle2, UserRound } from "lucide-react";
import { ConversationReadMarker } from "@/components/conversation-read-marker";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/format";
import { labelForChannel, labelForPriority, labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { InboxConversation, WorkspaceMember } from "@/lib/types";
import {
  assignHandoff,
  claimHandoff,
  replyToConversation,
  resolveHandoff,
  takeOverConversation,
} from "../actions";

const categoryLabels: Record<string, string> = {
  customer_request: "طلب من العميل",
  booking: "حجز أو موعد",
  payment: "دفع أو استرداد",
  complaint: "شكوى",
  medical: "استفسار يحتاج مراجعة",
  other: "متابعة عامة",
};

function senderLabel(senderType: string) {
  if (senderType === "patient") return "العميل";
  if (senderType === "staff") return "الفريق";
  if (senderType === "ai") return "Tia";
  return "العيادة";
}

function contextString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  const [conversation, ctx] = await Promise.all([
    tiaRequest<InboxConversation>(`/inbox/conversations/${conversationId}`),
    getAppContext(),
  ]);
  const members =
    ctx.workspace.role === "admin"
      ? await tiaRequest<WorkspaceMember[]>("/auth/workspace/members")
      : [];

  const handoff = conversation.active_handoff;
  const assignedToMe = handoff?.assigned_user_id === ctx.me.user.id;
  const unassigned = Boolean(handoff && !handoff.assigned_user_id);
  const assigneeName = conversation.assigned_user?.full_name || conversation.assigned_user?.email;
  const canResolve = Boolean(
    handoff && handoff.status !== "resolved" && (assignedToMe || ctx.workspace.role === "admin"),
  );
  const latestCustomerMessage = contextString(handoff?.context_json?.latest_customer_message);
  const patientName = `${conversation.patient.first_name} ${conversation.patient.last_name || ""}`.trim();

  return (
    <>
      <ConversationReadMarker
        conversationId={conversation.id}
        unreadCount={conversation.unread_count}
      />
      <PageHeader
        title={patientName}
        description={`${labelForChannel(conversation.channel)} · ${conversation.patient.phone || "لا يوجد رقم هاتف مسجل"}`}
        action={
          <Link href="/inbox" className={buttonVariants({ variant: "outline" })}>
            <ArrowRight size={15} /> المحادثات
          </Link>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="min-h-[650px] overflow-hidden">
          <CardHeader className="border-b border-[var(--border)] py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle>المحادثة</CardTitle>
              <div className="flex flex-wrap gap-2">
                <Badge tone={conversation.owner_type === "human" ? "yellow" : "green"}>
                  {conversation.owner_type === "human" ? "الفريق يتولى الرد" : "Tia تتولى الرد"}
                </Badge>
                <Badge tone={toneForStatus(conversation.status)}>{labelForStatus(conversation.status)}</Badge>
              </div>
            </div>
          </CardHeader>

          <CardContent className="flex min-h-[590px] flex-col p-0">
            <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
              {conversation.messages.map((message) => {
                const incoming = message.sender_type === "patient";
                const isAi = message.sender_type === "ai";
                return (
                  <div key={message.id} className={`flex ${incoming ? "justify-start" : "justify-end"}`}>
                    <div
                      className={`max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[76%] ${
                        incoming ? "bg-[var(--surface-2)]" : "bg-[#e4f4f1]"
                      }`}
                    >
                      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-bold text-[var(--muted)]">
                        {isAi ? <Bot size={12} /> : <UserRound size={12} />}
                        {senderLabel(message.sender_type)}
                      </div>
                      <div className="whitespace-pre-wrap text-sm leading-6">
                        {message.content || "رسالة بدون نص"}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-[var(--muted)]">
                        <span>{formatDateTime(message.created_at)}</span>
                        {message.direction === "outbound" && (
                          <span>{labelForStatus(message.delivery_status)}</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              {!conversation.messages.length && (
                <div className="py-16 text-center text-sm text-[var(--muted)]">لا توجد رسائل حتى الآن.</div>
              )}
            </div>

            <div className="border-t border-[var(--border)] bg-white p-4">
              {conversation.status === "closed" ? (
                <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                  هذه المحادثة مغلقة. يمكن متابعة العميل من ملفه عند الحاجة.
                </div>
              ) : conversation.owner_type === "ai" ? (
                <div className="flex flex-col gap-3 rounded-xl bg-teal-50 p-4 text-sm text-teal-900 sm:flex-row sm:items-center sm:justify-between">
                  <span>Tia تتولى المحادثة حاليًا. استلم المحادثة إذا احتاج الفريق إلى الرد مباشرة.</span>
                  <form action={takeOverConversation}>
                    <input type="hidden" name="conversation_id" value={conversation.id} />
                    <Button size="sm">استلام المحادثة</Button>
                  </form>
                </div>
              ) : handoff && assignedToMe ? (
                <form action={replyToConversation} className="flex flex-col gap-3 sm:flex-row">
                  <input type="hidden" name="conversation_id" value={conversation.id} />
                  <Textarea
                    name="content"
                    placeholder="اكتب ردك للعميل..."
                    className="min-h-20 flex-1"
                    required
                  />
                  <Button className="self-end">إرسال الرد</Button>
                </form>
              ) : handoff && unassigned ? (
                <div className="flex flex-col gap-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 sm:flex-row sm:items-center sm:justify-between">
                  <span>هذه المحادثة تحتاج متابعة من أحد أعضاء الفريق.</span>
                  <form action={claimHandoff}>
                    <input type="hidden" name="handoff_id" value={handoff.id} />
                    <input type="hidden" name="conversation_id" value={conversation.id} />
                    <Button size="sm">استلام المتابعة</Button>
                  </form>
                </div>
              ) : handoff ? (
                <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
                  يتابع هذه المحادثة <b>{assigneeName || "عضو آخر من الفريق"}</b>.
                </div>
              ) : (
                <div className="flex flex-col gap-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 sm:flex-row sm:items-center sm:justify-between">
                  <span>المحادثة بانتظار متابعة الفريق.</span>
                  <form action={takeOverConversation}>
                    <input type="hidden" name="conversation_id" value={conversation.id} />
                    <Button size="sm">استلام المحادثة</Button>
                  </form>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>متابعة المحادثة</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[var(--muted)]">المتابعة الحالية</span>
                  <b>{conversation.owner_type === "human" ? "الفريق" : "Tia"}</b>
                </div>
                {conversation.owner_type === "human" && (
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[var(--muted)]">المسؤول</span>
                    <span className="text-left font-bold">{assigneeName || "لم يتم الإسناد بعد"}</span>
                  </div>
                )}
                {conversation.unread_count > 0 && (
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[var(--muted)]">رسائل جديدة</span>
                    <Badge tone="blue">{conversation.unread_count}</Badge>
                  </div>
                )}
              </div>

              {handoff && (
                <div className="space-y-3 border-t border-[var(--border)] pt-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge tone={toneForStatus(handoff.priority)}>أولوية {labelForPriority(handoff.priority)}</Badge>
                    <Badge tone={toneForStatus(handoff.status)}>{labelForStatus(handoff.status)}</Badge>
                  </div>
                  <div>
                    <div className="text-xs font-bold text-[var(--muted)]">سبب المتابعة</div>
                    <p className="mt-1 leading-6">{handoff.reason}</p>
                  </div>
                  {handoff.category && (
                    <div className="text-xs text-[var(--muted)]">
                      {categoryLabels[handoff.category] || "متابعة من الفريق"}
                    </div>
                  )}
                  {latestCustomerMessage && latestCustomerMessage !== handoff.reason && (
                    <div className="rounded-xl bg-[var(--surface-2)] p-3">
                      <div className="text-xs font-bold text-[var(--muted)]">آخر رسالة مهمة</div>
                      <p className="mt-1 leading-6">{latestCustomerMessage}</p>
                    </div>
                  )}

                  {ctx.workspace.role === "admin" && handoff.status !== "resolved" && (
                    <form action={assignHandoff} className="space-y-2 border-t border-[var(--border)] pt-3">
                      <input type="hidden" name="handoff_id" value={handoff.id} />
                      <input type="hidden" name="conversation_id" value={conversation.id} />
                      <label className="block text-xs font-bold text-[var(--muted)]">إسناد المتابعة</label>
                      <select
                        name="user_id"
                        defaultValue={handoff.assigned_user_id || ""}
                        required
                        className="form-control h-10 min-h-10"
                      >
                        <option value="" disabled>اختر عضوًا من الفريق</option>
                        {members
                          .filter((member) => member.is_active)
                          .map((member) => (
                            <option key={member.user_id} value={member.user_id}>
                              {member.full_name || member.email}
                            </option>
                          ))}
                      </select>
                      <Button variant="outline" className="w-full">حفظ المسؤول</Button>
                    </form>
                  )}

                  {canResolve && (
                    <form action={resolveHandoff} className="space-y-3 border-t border-[var(--border)] pt-3">
                      <input type="hidden" name="handoff_id" value={handoff.id} />
                      <input type="hidden" name="conversation_id" value={conversation.id} />
                      <Textarea name="resolution_note" placeholder="ملاحظة ختامية - اختياري" />
                      <label className="flex items-start gap-2 text-xs leading-5 text-[var(--muted)]">
                        <input type="checkbox" name="close_conversation" className="mt-1" />
                        إغلاق المحادثة بعد إنهاء المتابعة
                      </label>
                      <Button variant="secondary" className="w-full">
                        <CheckCircle2 size={16} />
                        إنهاء المتابعة
                      </Button>
                    </form>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>العميل</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[var(--muted)]">رقم الهاتف</span>
                <b dir="ltr">{conversation.patient.phone || "—"}</b>
              </div>
              <Link href={`/patients/${conversation.patient.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                فتح ملف العميل
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
