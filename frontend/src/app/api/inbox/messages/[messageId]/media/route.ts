import { TiaApiError, tiaRawRequest } from "@/lib/tia/api";

export const dynamic = "force-dynamic";

const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "content-length",
  "content-range",
  "accept-ranges",
  "content-disposition",
] as const;

export async function GET(
  request: Request,
  { params }: { params: Promise<{ messageId: string }> },
) {
  const { messageId } = await params;
  const range = request.headers.get("range");
  const headers = new Headers();
  if (range) headers.set("Range", range);

  try {
    const response = await tiaRawRequest(
      `/inbox/messages/${encodeURIComponent(messageId)}/media`,
      {
        headers,
        signal: AbortSignal.timeout(90_000),
      },
    );
    const forwarded = new Headers({
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) forwarded.set(name, value);
    }
    return new Response(response.body, {
      status: response.status,
      headers: forwarded,
    });
  } catch (error) {
    const status = error instanceof TiaApiError ? error.status : 502;
    return new Response("Media is unavailable.", {
      status,
      headers: {
        "Cache-Control": "private, no-store",
        "Content-Type": "text/plain; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
      },
    });
  }
}
