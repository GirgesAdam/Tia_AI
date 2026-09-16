"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { replyToConversation, type ReplyActionState } from "../actions";

const initialState: ReplyActionState = { submittedRequestId: null };

export function InboxReplyForm({ conversationId }: { conversationId: string }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [draft, setDraft] = useState("");
  const [requestId, setRequestId] = useState("");
  const [state, formAction, isPending] = useActionState(replyToConversation, initialState);
  const storageKey = `tia:inbox-reply:${conversationId}`;

  useEffect(() => {
    let nextDraft = "";
    let nextRequestId = crypto.randomUUID();
    const raw = window.sessionStorage.getItem(storageKey);
    if (raw) {
      try {
        const saved = JSON.parse(raw) as { content?: unknown; requestId?: unknown };
        if (typeof saved.content === "string") nextDraft = saved.content;
        if (typeof saved.requestId === "string" && saved.requestId) {
          nextRequestId = saved.requestId;
        }
      } catch {
        window.sessionStorage.removeItem(storageKey);
      }
    }
    setDraft(nextDraft);
    setRequestId(nextRequestId);
  }, [storageKey]);

  useEffect(() => {
    if (!requestId) return;
    if (!draft) {
      window.sessionStorage.removeItem(storageKey);
      return;
    }
    window.sessionStorage.setItem(
      storageKey,
      JSON.stringify({ content: draft, requestId }),
    );
  }, [draft, requestId, storageKey]);

  useEffect(() => {
    if (!state.submittedRequestId || state.submittedRequestId !== requestId) return;
    window.sessionStorage.removeItem(storageKey);
    setDraft("");
    setRequestId(crypto.randomUUID());
  }, [requestId, state.submittedRequestId, storageKey]);

  return (
    <form ref={formRef} action={formAction} className="flex flex-col gap-3 sm:flex-row">
      <input type="hidden" name="conversation_id" value={conversationId} />
      <input type="hidden" name="request_id" value={requestId} />
      <Textarea
        name="content"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="اكتب ردك للعميل..."
        className="min-h-20 flex-1"
        required
        onKeyDown={(event) => {
          if (
            event.key !== "Enter" ||
            event.shiftKey ||
            event.nativeEvent.isComposing ||
            isPending ||
            !requestId ||
            !draft.trim()
          ) {
            return;
          }
          event.preventDefault();
          formRef.current?.requestSubmit();
        }}
      />
      <Button
        className="self-end"
        disabled={isPending || !requestId || !draft.trim()}
      >
        {isPending ? "جارٍ الإرسال..." : "إرسال الرد"}
      </Button>
    </form>
  );
}
