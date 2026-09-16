import Image from "next/image";
import { Download, FileText, Mic, Video } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import type { InboxMessage } from "@/lib/types";

const MEDIA_TYPES = new Set(["image", "audio", "video", "document", "sticker"]);

function mediaMetadata(message: InboxMessage): Record<string, unknown> {
  const raw = message.metadata_json?.media;
  return raw && typeof raw === "object" && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
}

function mediaString(message: InboxMessage, key: string) {
  const value = mediaMetadata(message)[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function InboxMessageBody({ message }: { message: InboxMessage }) {
  if (!MEDIA_TYPES.has(message.message_type)) {
    return (
      <div className="whitespace-pre-wrap text-sm leading-6">
        {message.content || "رسالة بدون نص"}
      </div>
    );
  }

  const mediaUrl = `/api/inbox/messages/${encodeURIComponent(message.id)}/media`;
  const filename = mediaString(message, "filename");
  const mimeType = mediaString(message, "mime_type");
  const caption = message.content?.trim() || null;

  return (
    <div className="space-y-2">
      {(message.message_type === "image" || message.message_type === "sticker") && (
        <a
          href={mediaUrl}
          target="_blank"
          rel="noreferrer"
          className="block overflow-hidden rounded-xl bg-white/70"
          aria-label={message.message_type === "sticker" ? "فتح الملصق" : "فتح الصورة"}
        >
          <Image
            unoptimized
            src={mediaUrl}
            alt={caption || (message.message_type === "sticker" ? "ملصق من العميل" : "صورة من العميل")}
            width={800}
            height={600}
            className="h-auto max-h-[420px] w-full object-contain"
          />
        </a>
      )}

      {message.message_type === "audio" && (
        <div className="space-y-2 rounded-xl bg-white/70 p-3">
          <div className="flex items-center gap-2 text-xs font-bold text-[var(--muted)]">
            <Mic size={14} /> رسالة صوتية
          </div>
          <audio controls preload="metadata" className="w-full" src={mediaUrl}>
            المتصفح لا يدعم تشغيل الرسالة الصوتية.
          </audio>
        </div>
      )}

      {message.message_type === "video" && (
        <div className="space-y-2 overflow-hidden rounded-xl bg-white/70 p-2">
          <div className="flex items-center gap-2 px-1 text-xs font-bold text-[var(--muted)]">
            <Video size={14} /> فيديو من العميل
          </div>
          <video
            controls
            preload="metadata"
            className="max-h-[420px] w-full rounded-lg bg-black object-contain"
            src={mediaUrl}
          >
            المتصفح لا يدعم تشغيل الفيديو.
          </video>
        </div>
      )}

      {message.message_type === "document" && (
        <a
          href={mediaUrl}
          className={buttonVariants({ variant: "outline", size: "sm" })}
          title={mimeType || undefined}
        >
          <FileText size={16} />
          <span className="max-w-[230px] truncate">{filename || "تحميل الملف المرسل"}</span>
          <Download size={14} />
        </a>
      )}

      {caption && <div className="whitespace-pre-wrap text-sm leading-6">{caption}</div>}
    </div>
  );
}
