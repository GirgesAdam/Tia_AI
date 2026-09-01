import { NextResponse } from "next/server";

import { TiaApiError, tiaRawRequest } from "@/lib/tia/api";

export async function POST(request: Request) {
  try {
    const body = await request.text();
    const response = await tiaRawRequest("/analytics/catalog/export", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
    });
    const headers = new Headers();
    headers.set("Content-Type", response.headers.get("Content-Type") || "text/csv; charset=utf-8");
    const disposition = response.headers.get("Content-Disposition");
    if (disposition) headers.set("Content-Disposition", disposition);
    return new Response(response.body, { status: 200, headers });
  } catch (error) {
    const status = error instanceof TiaApiError ? error.status : 500;
    const message = error instanceof Error ? error.message : "Analytics export failed.";
    return NextResponse.json({ detail: message }, { status });
  }
}
