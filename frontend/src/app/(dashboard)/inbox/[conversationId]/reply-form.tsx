"use client";

import { useActionState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { replyToConversation, type ReplyActionState } from "../actions";

const initialState: ReplyActionState = { submittedRequestId: null };

export function InboxReplyForm({ conversationId }: { conversationId: string }) {
  const formRef = useRef<HTMLFormElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const requestInputRef = useRef<HTMLInputElement>(null);
  const requestIdRef = useRef<string | null>(null);
  const [state, formAction, isPending] = useActionState(replyToConversation, initialState);
  const storageKey = `tia:inbox-reply:${conversationId}`;

  const ensureRequestId = () => {
    let requestId = requestIdRef.current;
    if (!requestId) {
      requestId = crypto.randomUUID();
      requestIdRef.current = requestId;
      if (requestInputRef.current) requestInputRef.current.value = requestId;
    }
    return requestId;
  };

  useEffect(() => {
    const raw = window.sessionStorage.getItem(storageKey);
    if (!raw) return;
    try {
      const saved = JSON.parse(raw) as { content?: unknown; requestId?: unknown };
      if (typeof saved.content === "string" && textareaRef.current) {
        textareaRef.current.value = saved.content;
      }
      if (typeof saved.requestId === "string" && saved.requestId) {
        requestIdRef.current = saved.requestId;
        if (requestInputRef.current) requestInputRef.current.value = saved.requestId;
      }
    } catch {
      window.sessionStorage.removeItem(storageKey);
    }
  }, [storageKey]);

  useEffect(() => {
    if (!state.submittedRequestId || state.submittedRequestId !== requestIdRef.current) return;
    window.sessionStorage.removeItem(storageKey);
    if (textareaRef.current) textareaRef.current.value = "";
    const nextRequestId = crypto.randomUUID();
    requestIdRef.current = nextRequestId;
    if (requestInputRef.current) requestInputRef.current.value = nextRequestId;
  }, [state.submittedRequestId, storageKey]);

  return (
    <form ref={formRef} action={formAction} className="flex flex-col gap-3 sm:flex-row">
      <input type="hidden" name="conversation_id" value={conversationId} />
      <input ref={requestInputRef} type="hidden" name="request_id" />
      <Textarea
        ref={textareaRef}
        name="content"
        placeholder="اكتب ردك للعميل..."
        className="min-h-20 flex-1"
        required
        onChange={(event) => {
          const content = event.currentTarget.value;
          if (!content) {
            window.sessionStorage.removeItem(storageKey);
            return;
          }
          window.sessionStorage.setItem(
            storageKey,
            JSON.stringify({ content, requestId: ensureRequestId() }),
          );
        }}
        onKeyDown={(event) => {
          if (
            event.key !== "Enter" ||
            event.shiftKey ||
            event.nativeEvent.isComposing ||
            isPending ||
            !event.currentTarget.value.trim()
          ) {
            return;
          }
          event.preventDefault();
          ensureRequestId();
          formRef.current?.requestSubmit();
        }}
      />
      <Button
        className="self-end"
        disabled={isPending}
        onClick={() => ensureRequestId()}
      >
        {isPending ? "جارٍ الإرسال..." : "إرسال الرد"}
      </Button>
    </form>
  );
}
