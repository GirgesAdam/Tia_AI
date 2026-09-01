"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { markConversationRead } from "@/app/(dashboard)/inbox/actions";

export function ConversationReadMarker({
  conversationId,
  unreadCount,
}: {
  conversationId: string;
  unreadCount: number;
}) {
  const router = useRouter();

  useEffect(() => {
    if (unreadCount <= 0) return;
    let active = true;
    void markConversationRead(conversationId)
      .then(() => {
        if (active) router.refresh();
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [conversationId, router, unreadCount]);

  return null;
}
