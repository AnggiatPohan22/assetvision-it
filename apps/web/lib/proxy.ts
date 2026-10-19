const endpoints = new Map<string, readonly string[]>([
  ["health", ["GET"]], ["ready", ["GET"]], ["auth/csrf", ["GET"]],
  ["auth/login", ["POST"]], ["auth/logout", ["POST"]], ["auth/me", ["GET"]],
  ["auth/session", ["GET"]], ["admin/status", ["GET"]],
]);
const MAX_BODY_BYTES = 16384;
const MAX_CSV_REQUEST_BYTES = 1024 * 1024;
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024 + 65536;
const catalogResources = new Set(["device-categories", "manufacturers", "device-models"]);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function proxyError(detail: string, status: number): Response {
  return Response.json({ detail }, {
    status, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}

function allowedMethods(path: string[]): readonly string[] | undefined {
  const existing = endpoints.get(path.join("/"));
  if (existing) return existing;
  if (path[0] === "movements") {
    if (path.length === 1) return ["GET"];
    if (path.length === 2 && uuid.test(path[1])) return ["GET"];
    if (path.length === 3 && uuid.test(path[1]) && ["approve", "reject", "cancel"].includes(path[2])) return ["POST"];
    return undefined;
  }
  if (path[0] === "locations") {
    if (path.length === 1) return ["GET", "POST"];
    if (path.length === 2 && path[1] === "tree") return ["GET"];
    if (path.length === 2 && uuid.test(path[1])) return ["GET", "PATCH"];
    return undefined;
  }
  if (path[0] === "assets") {
    if (path.length === 2 && path[1] === "export.csv") return ["GET"];
    if (path.length === 3 && path[1] === "imports" && ["preview", "commit"].includes(path[2])) return ["POST"];
    if (path.length === 1) return ["GET", "POST"];
    if (!uuid.test(path[1])) return undefined;
    if (path.length === 2) return ["GET", "PATCH"];
    if (path.length === 3 && path[2] === "archive") return ["POST"];
    if (path.length === 3 && path[2] === "location") return ["GET"];
    if (path.length === 3 && path[2] === "initial-placement") return ["POST"];
    if (path.length === 3 && path[2] === "movements") return ["GET", "POST"];
    if (path.length === 3 && path[2] === "events") return ["GET"];
    if (path[2] === "identifiers") {
      if (path.length === 3) return ["GET", "POST"];
      if (path.length === 4 && uuid.test(path[3])) return ["PATCH", "DELETE"];
    }
    return undefined;
  }
  if (!catalogResources.has(path[0])) return undefined;
  if (path.length === 1) return ["GET", "POST"];
  if (!uuid.test(path[1])) return undefined;
  if (path.length === 2) return ["GET", "PATCH"];
  if (path.length === 3 && path[0] === "device-models" && path[2] === "archive")
    return ["POST"];
  if (path[0] === "device-models" && path[2] === "reference-images") {
    if (path.length === 3) return ["GET", "POST"];
    if (uuid.test(path[3])) {
      if (path.length === 4) return ["DELETE"];
      if (path.length === 5 && path[4] === "content") return ["GET"];
    }
  }
  return undefined;
}

async function readBody(request: Request, limit = MAX_BODY_BYTES): Promise<ArrayBuffer | Response> {
  if (Number(request.headers.get("content-length") ?? 0) > limit)
    return proxyError("Request too large", 413);
  const reader = request.body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (reader) {
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > limit) {
          await reader.cancel().catch(() => undefined);
          return proxyError("Request too large", 413);
        }
        chunks.push(value);
      }
    } catch {
      return proxyError("Invalid request body", 400);
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
  const methods = allowedMethods(path);
  if (!methods) return proxyError("Not found", 404);
  if (!methods.includes(request.method))
    return proxyError("Method not allowed", 405);
  const headers = new Headers();
  for (const name of ["cookie", "content-type", "origin", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  let body: ArrayBuffer | undefined;
  if (request.method === "POST" || request.method === "PATCH") {
    const imageUpload = path.length === 3 && path[0] === "device-models" && path[2] === "reference-images";
    const csvImport = path.length === 3 && path[0] === "assets" && path[1] === "imports";
    const limit = imageUpload ? MAX_UPLOAD_BYTES : csvImport ? MAX_CSV_REQUEST_BYTES : MAX_BODY_BYTES;
    const result = await readBody(request, limit);
    if (result instanceof Response) return result;
    body = result;
  }
  try {
    const upstream = await fetch(
      `${process.env.INTERNAL_API_URL ?? "http://api:8000"}/api/v1/${endpoint}${new URL(request.url).search}`,
      { method: request.method, headers, body, cache: "no-store",
        redirect: "manual", signal: AbortSignal.timeout(30000) },
    );
    const outgoing = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "x-request-id", "content-disposition", "x-model-version", "x-content-type-options"]) {
      const value = upstream.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append("set-cookie", cookie);
    return new Response(upstream.body, { status: upstream.status, headers: outgoing });
  } catch {
    return proxyError("API unavailable", 503);
  }
}
