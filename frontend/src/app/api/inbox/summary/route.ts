import { NextResponse } from "next/server";

import { tiaRequest } from "@/lib/tia/api";

export const dynamic = "force-dynamic";

type InboxConversationListItem = Record<string, unknown>;

export async function GET() {
  const conversations = await tiaRequest<InboxConversationListItem[]>(
    "/inbox/conversations?status=open&unread_only=true&limit=100&offset=0",
  ).catch(() => null);

  if (!conversations) {
    return NextResponse.json(
      { error: "Unable to load inbox summary." },
      { status: 502 },
    );
  }

  return NextResponse.json(
    { unread_conversations: conversations.length },
    { headers: { "Cache-Control": "no-store" } },
  );
}
