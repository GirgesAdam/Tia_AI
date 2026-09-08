"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { replyToConversation } from "../actions";

export function InboxReplyForm({ conversationId }: { conversationId: string }) {
  const formRef = useRef<HTMLFormElement>(null);

  return (
    <form ref={formRef} action={replyToConversation} className="flex flex-col gap-3 sm:flex-row">
      <input type="hidden" name="conversation_id" value={conversationId} />
      <Textarea
        name="content"
        placeholder="اكتب ردك للعميل..."
        className="min-h-20 flex-1"
        required
        onKeyDown={(event) => {
          if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
            return;
          }
          event.preventDefault();
          formRef.current?.requestSubmit();
        }}
      />
      <Button className="self-end">إرسال الرد</Button>
    </form>
  );
}
