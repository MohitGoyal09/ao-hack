import { NextRequest, NextResponse } from "next/server";

const upstream = process.env.AGENT_URL ?? "http://localhost:8123";

// Same-origin proxy to the FastAPI service. Forwards the caller's bearer and
// the body untouched (JSON or multipart) and preserves the upstream status and
// `{detail}`. DEMO_BEARER (server env, offline dev convenience only) is injected
// when the browser sends no Authorization header.
async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const headers: Record<string, string> = {};
  const demo = process.env.DEMO_BEARER;
  const auth = request.headers.get("authorization") ?? (demo ? (demo.startsWith("Bearer ") ? demo : `Bearer ${demo}`) : null);
  if (auth) headers.authorization = auth;
  const contentType = request.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  try {
    const response = await fetch(`${upstream}/api/${path.join("/")}${request.nextUrl.search}`, { method: request.method, headers, body, cache: "no-store" });
    return new NextResponse(response.body, { status: response.status, headers: { "content-type": response.headers.get("content-type") ?? "application/json" } });
  } catch {
    return NextResponse.json({ detail: "Covenant API unavailable" }, { status: 503 });
  }
}

export { forward as GET, forward as POST, forward as PATCH, forward as DELETE };
