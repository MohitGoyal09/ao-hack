import { NextRequest, NextResponse } from "next/server";

const upstream = process.env.AGENT_URL ?? "http://localhost:8123";

export async function GET(_request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward("GET", context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward("POST", context, await request.text());
}

async function forward(method: "GET" | "POST", context: { params: Promise<{ path: string[] }> }, body?: string) {
  const { path } = await context.params;
  try {
    const response = await fetch(`${upstream}/api/${path.join("/")}`, { method, headers: body ? { "content-type": "application/json" } : undefined, body, cache: "no-store" });
    return new NextResponse(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return NextResponse.json({ detail: "Covenant API unavailable" }, { status: 503 });
  }
}
