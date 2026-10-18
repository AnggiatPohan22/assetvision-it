const endpoints = new Map<string, readonly string[]>([
  ["health", ["GET"]], ["ready", ["GET"]], ["auth/csrf", ["GET"]],
  ["auth/login", ["POST"]], ["auth/logout", ["POST"]], ["auth/me", ["GET"]],
  ["auth/session", ["GET"]], ["admin/status", ["GET"]],
]);
const MAX_BODY_BYTES = 16384;

async function readBody(request: Request): Promise<ArrayBuffer | Response> {
  if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY_BYTES)
    return Response.json({ detail: "Request too large" }, { status: 413 });
  const reader = request.body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (reader) {
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_BODY_BYTES) {
          await reader.cancel().catch(() => undefined);
          return Response.json({ detail: "Request too large" }, { status: 413 });
        }
        chunks.push(value);
      }
    } catch {
      return Response.json({ detail: "Invalid request body" }, { status: 400 });
    } finally {
      reader.releaseLock();
    }
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

export async function proxyRequest(request: Request, path: string[]): Promise<Response> {
  const endpoint = path.join("/");
  const methods = endpoints.get(endpoint);
  if (!methods) return Response.json({ detail: "Not found" }, { status: 404 });
  if (!methods.includes(request.method))
    return Response.json({ detail: "Method not allowed" }, { status: 405 });
  const headers = new Headers();
  for (const name of ["cookie", "content-type", "origin", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  let body: ArrayBuffer | undefined;
  if (request.method === "POST") {
    const result = await readBody(request);
    if (result instanceof Response) return result;
    body = result;
  }
  try {
    const upstream = await fetch(
      `${process.env.INTERNAL_API_URL ?? "http://api:8000"}/api/v1/${endpoint}`,
      { method: request.method, headers, body, cache: "no-store",
        redirect: "manual", signal: AbortSignal.timeout(10000) },
    );
    const outgoing = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "x-request-id"]) {
      const value = upstream.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append("set-cookie", cookie);
    return new Response(upstream.body, { status: upstream.status, headers: outgoing });
  } catch {
    return Response.json({ detail: "API unavailable" },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
