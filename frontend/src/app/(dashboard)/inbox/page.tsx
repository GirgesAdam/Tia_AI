import Link from "next/link";
import { Bot, MessageSquareMore, UserRound } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { FilterChip } from "@/components/ui/filter-chip";
import { formatDateTime } from "@/lib/format";
import { labelForChannel, labelForPriority, labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import type { InboxConversationListItem } from "@/lib/types";

type InboxSearchParams = { owner?: string; status?: string; mine?: string; unread?: string };

const ownerOptions = [["", "الكل"], ["human", "الفريق"], ["ai", "Tia"]] as const;
const statusOptions = [["", "كل الحالات"], ["open", "مفتوحة"], ["pending", "بانتظار رد"], ["closed", "مغلقة"]] as const;

function filterHref(current: InboxSearchParams, key: keyof InboxSearchParams, value: string) {
  const params = new URLSearchParams();
  for (const [currentKey, currentValue] of Object.entries(current)) {
    if (currentValue && currentKey !== key) params.set(currentKey, currentValue);
  }
  if (value) params.set(key, value);
  const query = params.toString();
  return query ? `/inbox?${query}` : "/inbox";
}

function senderLabel(senderType?: string) {
  if (senderType === "patient") return "العميل";
  if (senderType === "staff") return "الفريق";
  if (senderType === "ai") return "Tia";
  return "رسالة";
}


export default async function InboxPage({ searchParams }: { searchParams: Promise<InboxSearchParams> }) {
  const raw = await searchParams;
  const filters: InboxSearchParams = {
    owner: raw.owner === "ai" || raw.owner === "human" ? raw.owner : "",
    status: ["open", "pending", "closed"].includes(raw.status || "") ? raw.status : "",
    mine: raw.mine === "1" ? "1" : "",
    unread: raw.unread === "1" ? "1" : "",
  };

  const query = new URLSearchParams({ limit: "100" });
  if (filters.owner) query.set("owner_type", filters.owner);
  if (filters.status) query.set("status", filters.status);
  if (filters.mine) query.set("assigned_to_me", "true");
  if (filters.unread) query.set("unread_only", "true");

  const conversations = await tiaRequest<InboxConversationListItem[]>(`/inbox/conversations?${query.toString()}`);

  return (
    <>
      <PageHeader
        title="الرسائل"
        description="كل محادثات العملاء في مكان واحد، مع توضيح المحادثات التي تديرها Tia والمحادثات التي تحتاج تدخل الفريق."
      />

      <div className="surface-toolbar mb-4">
        {ownerOptions.map(([value, label]) => (
          <FilterChip key={value || "all"} href={filterHref(filters, "owner", value)} active={filters.owner === value}>
            {label}
          </FilterChip>
        ))}
        <span className="mx-1 hidden h-8 w-px bg-slate-200 sm:block" />
        {statusOptions.map(([value, label]) => (
          <FilterChip key={value || "all"} href={filterHref(filters, "status", value)} active={filters.status === value}>
            {label}
          </FilterChip>
        ))}
        <FilterChip href={filterHref(filters, "mine", filters.mine ? "" : "1")} active={Boolean(filters.mine)}>
          مسندة لي
        </FilterChip>
        <FilterChip href={filterHref(filters, "unread", filters.unread ? "" : "1")} active={Boolean(filters.unread)}>
          غير مقروءة
        </FilterChip>
      </div>

      <Card>
        <CardContent className="p-0">
          {conversations.length ? (
            <div className="divide-y divide-[var(--border)]">
              {conversations.map((conversation) => {
                const patientName = `${conversation.patient.first_name} ${conversation.patient.last_name || ""}`.trim();
                const preview = conversation.last_message?.content?.trim() || (conversation.last_message ? "رسالة غير نصية" : "لا توجد رسائل بعد");
                const assignee = conversation.assigned_user?.full_name || conversation.assigned_user?.email;
                return (
                  <Link
                    href={`/inbox/${conversation.id}`}
                    key={conversation.id}
                    className="grid gap-3 p-4 transition hover:bg-slate-50 sm:p-5 md:grid-cols-[minmax(190px,.8fr)_minmax(260px,1.5fr)_auto] md:items-center"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="truncate font-bold text-slate-900">{patientName}</div>
                        {conversation.unread_count > 0 && (
                          <span className="grid min-w-6 place-items-center rounded-full bg-teal-700 px-1.5 py-0.5 text-[10px] font-black text-white">
                            {conversation.unread_count}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 truncate text-xs text-[var(--muted)]">
                        {conversation.patient.phone || "بدون رقم هاتف"} · {labelForChannel(conversation.channel)}
                      </div>
                    </div>

                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={conversation.owner_type === "human" ? "yellow" : "green"}>
                          <span className="inline-flex items-center gap-1">
                            {conversation.owner_type === "human" ? <UserRound size={11} /> : <Bot size={11} />}
                            {conversation.owner_type === "human" ? "مع الفريق" : "تديرها Tia"}
                          </span>
                        </Badge>
                        <Badge tone={toneForStatus(conversation.status)}>{labelForStatus(conversation.status)}</Badge>
                        {conversation.active_handoff && (
                          <Badge tone={toneForStatus(conversation.active_handoff.priority)}>
                            متابعة {labelForPriority(conversation.active_handoff.priority)}
                          </Badge>
                        )}
                        {assignee && <Badge>{assignee}</Badge>}
                      </div>
                      <p className="mt-2 truncate text-sm text-[var(--muted)]">
                        <span className="font-semibold text-[var(--text)]">{senderLabel(conversation.last_message?.sender_type)}:</span> {preview}
                      </p>
                    </div>

                    <div className="whitespace-nowrap text-[11px] font-semibold text-[var(--muted)] md:text-xs">
                      {formatDateTime(conversation.last_message_at || conversation.started_at)}
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={MessageSquareMore}
              title="لا توجد محادثات مطابقة"
              description="غيّر الفلاتر أو افتح كل المحادثات لعرض نتائج أخرى."
            />
          )}
        </CardContent>
      </Card>
    </>
  );
}
