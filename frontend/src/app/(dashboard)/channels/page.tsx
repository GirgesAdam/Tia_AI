import { MessageCircleMore, RadioTower } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";
import { labelForChannel, labelForStatus, toneForStatus } from "@/lib/status";
import { tiaRequest } from "@/lib/tia/api";
import { getAppContext } from "@/lib/tia/workspace";
import type { ChannelConnection } from "@/lib/types";
import { updateAiFollowupTemplate } from "./actions";

function followupTemplate(connection: ChannelConnection) {
  const value = connection.config_json?.ai_followup_template;
  if (!value || typeof value !== "object" || Array.isArray(value)) return { name: "", language: "ar" };
  const row = value as Record<string, unknown>;
  return {
    name: typeof row.name === "string" ? row.name : "",
    language: typeof row.language_code === "string" ? row.language_code : "ar",
  };
}

export default async function ChannelsPage() {
  const [channels, ctx] = await Promise.all([
    tiaRequest<ChannelConnection[]>("/channels/connections"),
    getAppContext(),
  ]);

  return (
    <>
      <PageHeader
        title="قنوات التواصل"
        description="راجع القنوات المتصلة بالعيادة وحالتها الحالية. الإعدادات التقنية مخفية إلا عند الحاجة."
      />

      {channels.length ? (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {channels.map((connection) => {
            const template = followupTemplate(connection);
            return (
              <Card key={connection.id}>
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <span className="grid size-11 place-items-center rounded-xl bg-teal-50 text-teal-700">
                      {connection.channel === "whatsapp" ? <MessageCircleMore /> : <RadioTower />}
                    </span>
                    <Badge tone={toneForStatus(connection.status)}>{labelForStatus(connection.status)}</Badge>
                  </div>

                  <h3 className="mt-5 font-black text-slate-950">{connection.display_name}</h3>
                  <div className="mt-1 text-sm text-[var(--muted)]">{labelForChannel(connection.channel)}</div>
                  <div className="mt-4 border-t border-[var(--border)] pt-3 text-xs text-[var(--muted)]">
                    آخر تحديث: {formatDateTime(connection.updated_at)}
                  </div>

                  {connection.channel === "whatsapp" && ctx.workspace.role === "admin" && (
                    <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                      <summary className="cursor-pointer text-xs font-bold text-slate-600">إعدادات واتساب المتقدمة</summary>
                      <div className="mt-3 text-[11px] leading-5 text-[var(--muted)]">
                        استخدم قالبًا معتمدًا من Meta للمتابعات التي تُرسل خارج نافذة المحادثة.
                      </div>
                      <form action={updateAiFollowupTemplate} className="mt-3 space-y-2">
                        <input type="hidden" name="connection_id" value={connection.id} />
                        <Input name="template_name" defaultValue={template.name} placeholder="اسم القالب" dir="ltr" />
                        <Input name="template_language" defaultValue={template.language} placeholder="ar" dir="ltr" />
                        <Button size="sm" variant="outline">حفظ الإعدادات</Button>
                      </form>
                    </details>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={MessageCircleMore}
              title="لا توجد قناة تواصل متصلة"
              description="بعد ربط واتساب أو أي قناة أخرى ستظهر هنا مع حالتها الحالية."
            />
          </CardContent>
        </Card>
      )}
    </>
  );
}
