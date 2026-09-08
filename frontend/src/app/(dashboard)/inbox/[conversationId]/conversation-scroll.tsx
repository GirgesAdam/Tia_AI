"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export function ConversationScroll({
  messageCount,
  children,
}: {
  messageCount: number;
  children: ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const initializedRef = useRef(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    if (!initializedRef.current || stickToBottomRef.current) {
      container.scrollTop = container.scrollHeight;
    }
    initializedRef.current = true;
  }, [messageCount]);

  return (
    <div
      ref={containerRef}
      onScroll={(event) => {
        const container = event.currentTarget;
        const distanceFromBottom =
          container.scrollHeight - container.scrollTop - container.clientHeight;
        stickToBottomRef.current = distanceFromBottom < 96;
      }}
      className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain p-4 sm:p-5"
    >
      {children}
    </div>
  );
}
