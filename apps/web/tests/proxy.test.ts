import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { proxyRequest } from "../lib/proxy";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test("CSV proxy limits import bodies and preserves export bytes and headers", async () => {
  let calls = 0;
  globalThis.fetch = async (url, init) => {
    calls++;
    assert.equal(new Headers(init?.headers).get("cookie"), "av_access=opaque");
    if (String(url).includes("export.csv")) {
      assert.equal(new URL(String(url)).searchParams.get("status"), "ARCHIVED");
      return new Response("\ufeffasset_code,notes\r\nAP-001,'=1+1\r\n", { headers: {
        "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="assets.csv"',
      } });
    }
    assert.equal((init?.body as ArrayBuffer).byteLength, 20000);
    assert.equal(new Headers(init?.headers).get("x-csrf-token"), "csrf");
    return Response.json({ status: "REJECTED", created_count: 0 }, { status: 409 });
  };
  for (const action of ["preview", "commit"]) {
    const response = await proxyRequest(new Request("http://local", { method: "POST", body: "x".repeat(20000),
      headers: { cookie: "av_access=opaque", "x-csrf-token": "csrf" },
    }), ["assets", "imports", action]);
    assert.equal(response.status, 409);
  }
  const exported = await proxyRequest(new Request("http://local?status=ARCHIVED", {
    headers: { cookie: "av_access=opaque" },
  }), ["assets", "export.csv"]);
  assert.equal(exported.headers.get("content-disposition"), 'attachment; filename="assets.csv"');
  assert.equal(exported.headers.get("content-type"), "text/csv; charset=utf-8");
  assert.equal(new Uint8Array(await exported.arrayBuffer())[0], 0xef);
  assert.equal(exported.headers.get("cache-control"), "no-store");
  const before = calls;
  assert.equal((await proxyRequest(new Request("http://local", { method: "POST", body: "x".repeat(1024 * 1024 + 1) }), ["assets", "imports", "commit"])).status, 413);
  assert.equal((await proxyRequest(new Request("http://local"), ["assets", "imports", "preview"])).status, 405);
  assert.equal((await proxyRequest(new Request("http://local", { method: "POST" }), ["assets", "export.csv"])).status, 405);
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) { controller.enqueue(new Uint8Array(256 * 1024)); },
    cancel() { cancelled = true; },
  });
  assert.equal((await proxyRequest(new Request("http://local", {
    method: "POST", body: stream, duplex: "half",
  } as RequestInit & { duplex: "half" }), ["assets", "imports", "preview"])).status, 413);
  assert.equal(cancelled, true);
  assert.equal(calls, before);
});

test("asset proxy allows only CRUD and identifier routes, preserving versions and conflicts", async () => {
  const id = "00000000-0000-0000-0000-000000000001";
  let calls = 0;
  globalThis.fetch = async (url, init) => {
    calls++;
    assert.equal(new Headers(init?.headers).get("cookie"), "av_access=opaque");
    assert.equal(new URL(String(url)).search, "?version=2&asset_version=3");
    return Response.json({ detail: "Asset metadata changed; reload and retry" }, { status: 409 });
  };
  const routes: [string[], string[]][] = [
    [["assets"], ["GET", "POST"]], [["assets", id], ["GET", "PATCH"]],
    [["assets", id, "archive"], ["POST"]],
    [["assets", id, "events"], ["GET"]],
    [["assets", id, "identifiers"], ["GET", "POST"]],
    [["assets", id, "identifiers", id], ["PATCH", "DELETE"]],
  ];
  for (const [path, methods] of routes) for (const method of methods) {
    const response = await proxyRequest(new Request("http://local?version=2&asset_version=3", {
      method, headers: { cookie: "av_access=opaque", "x-csrf-token": "csrf" },
      ...(method === "PATCH" || method === "POST" ? { body: '{"version":2}' } : {}),
    }), path);
    assert.equal(response.status, 409);
    assert.equal(response.headers.get("cache-control"), "no-store");
  }
  const before = calls;
  for (const path of [["assets", "imports", "invalid"], ["assets", "imports"],
    ["assets", id, "photos"], ["assets", "invalid"], ["assets", id, "identifiers", "invalid"]])
    assert.equal((await proxyRequest(new Request("http://local"), path)).status, 404);
  assert.equal((await proxyRequest(new Request("http://local", { method: "DELETE" }), ["assets", id])).status, 405);
  assert.equal((await proxyRequest(new Request("http://local", { method: "POST" }), ["assets", id, "events"])).status, 405);
  assert.equal((await proxyRequest(new Request("http://local", { method: "PATCH", body: "x".repeat(17000) }), ["assets", id])).status, 413);
  assert.equal(calls, before);
});

test("proxy preserves 401/403 and each cookie without exposing an access-token body", async () => {
  for (const status of [401, 403, 200]) {
    globalThis.fetch = async (_url, init) => {
      const headers = new Headers(init?.headers);
      assert.equal(headers.get("origin"), "http://localhost:3000");
      assert.equal(headers.get("x-csrf-token"), "csrf");
      assert.equal(headers.get("authorization"), null);
      const response = new Response(JSON.stringify({ detail: "response" }), { status });
      response.headers.append("set-cookie", "av_access=opaque; HttpOnly; Path=/");
      response.headers.append("set-cookie", "av_csrf=csrf; HttpOnly; Path=/");
      return response;
    };
    const response = await proxyRequest(new Request("http://localhost/api/v1/auth/login", {
      method: "POST", headers: { origin: "http://localhost:3000", "x-csrf-token": "csrf",
        authorization: "should-not-forward" }, body: "{}",
    }), ["auth", "login"]);
    assert.equal(response.status, status);
    assert.equal(response.headers.getSetCookie().length, 2);
    assert.equal(response.headers.get("cache-control"), "no-store");
  }
});
test("proxy rejects unknown routes and unsupported methods", async () => {
  globalThis.fetch = async () => { throw new Error("must not call upstream"); };
  assert.equal((await proxyRequest(new Request("http://local"), ["evil"])).status, 404);
  assert.equal((await proxyRequest(new Request("http://local", { method: "DELETE" }),
    ["auth", "login"])).status, 405);
});
test("proxy reports API outages as 503", async () => {
  globalThis.fetch = async () => { throw new Error("offline"); };
  assert.equal((await proxyRequest(new Request("http://local"), ["auth", "me"])).status, 503);
});

test("catalog proxy forwards filters, PATCH body and safe conflict responses", async () => {
  const id = "00000000-0000-0000-0000-000000000001";
  globalThis.fetch = async (url, init) => {
    const target = new URL(String(url));
    assert.equal(target.pathname, `/api/v1/device-models/${id}`);
    assert.equal(target.searchParams.get("search"), "AP & outdoor");
    assert.equal(target.searchParams.get("page"), "2");
    assert.equal(init?.method, "PATCH");
    assert.equal(new TextDecoder().decode(init?.body as ArrayBuffer), '{"version":1,"model_name":"AP"}');
    assert.equal(new Headers(init?.headers).get("x-csrf-token"), "csrf");
    return Response.json({ detail: "Catalog record changed; reload and retry" }, { status: 409 });
  };
  const request = new Request(`http://local/api/v1/device-models/${id}?search=AP%20%26%20outdoor&page=2`, {
    method: "PATCH", body: '{"version":1,"model_name":"AP"}',
    headers: { "x-csrf-token": "csrf", "content-type": "application/json" },
  });
  const response = await proxyRequest(request, ["device-models", id]);
  assert.equal(response.status, 409);
  assert.equal((await response.json()).detail, "Catalog record changed; reload and retry");
});

test("catalog proxy allowlists collections, detail and archive without master delete access", async () => {
  const id = "00000000-0000-0000-0000-000000000001";
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({}); };
  for (const resource of ["device-categories", "manufacturers", "device-models"]) {
    for (const method of ["GET", "POST"])
      assert.equal((await proxyRequest(new Request("http://local", { method }), [resource])).status, 200);
    assert.equal((await proxyRequest(new Request("http://local"), [resource, id])).status, 200);
    assert.equal((await proxyRequest(new Request("http://local", { method: "DELETE" }), [resource, id])).status, 405);
  }
  assert.equal((await proxyRequest(new Request("http://local", { method: "POST" }), ["device-models", id, "archive"])).status, 200);
  const before = calls;
  for (const path of [["device-models", id, "reference-images", "invalid"], ["manufacturers", id, "archive"],
    ["device-models", ".."], ["device-models", "https://evil.example"], ["device-models/../auth", "login"]])
    assert.equal((await proxyRequest(new Request("http://local"), path)).status, 404);
  assert.equal(calls, before);
});

test("catalog PATCH retains the body size limit", async () => {
  globalThis.fetch = async () => { throw new Error("must not call upstream"); };
  const response = await proxyRequest(new Request("http://local", {
    method: "PATCH", body: "x".repeat(17000),
  }), ["device-models", "00000000-0000-0000-0000-000000000001"]);
  assert.equal(response.status, 413);
});

test("reference image proxy allows bounded multipart and authenticated content/delete", async () => {
  const id = "00000000-0000-0000-0000-000000000001";
  const collection = ["device-models", id, "reference-images"];
  globalThis.fetch = async (_url, init) => {
    assert.equal(new Headers(init?.headers).get("cookie"), "av_access=opaque");
    if (init?.method === "POST") {
      assert.equal((init.body as ArrayBuffer).byteLength, 20000);
      assert.equal(new Headers(init.headers).get("content-type"), "multipart/form-data; boundary=test");
      return Response.json({ model_version: 2 }, { status: 201 });
    }
    if (init?.method === "DELETE") return new Response(null, { status: 204, headers: { "X-Model-Version": "3" } });
    return new Response(new Uint8Array([1, 2, 3]), {
      headers: { "Content-Type": "image/png", "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff" },
    });
  };
  const upload = await proxyRequest(new Request("http://local", {
    method: "POST", body: "x".repeat(20000),
    headers: { cookie: "av_access=opaque", "content-type": "multipart/form-data; boundary=test" },
  }), collection);
  assert.equal(upload.status, 201);
  const content = await proxyRequest(new Request("http://local", { headers: { cookie: "av_access=opaque" } }), [...collection, id, "content"]);
  assert.equal(content.headers.get("content-type"), "image/png");
  assert.equal(content.headers.get("x-content-type-options"), "nosniff");
  assert.deepEqual(new Uint8Array(await content.arrayBuffer()), new Uint8Array([1, 2, 3]));
  const removed = await proxyRequest(new Request("http://local?version=2", { method: "DELETE", headers: { cookie: "av_access=opaque" } }), [...collection, id]);
  assert.equal(removed.status, 204);
  assert.equal(removed.headers.get("x-model-version"), "3");
});

test("reference upload rejects excessive streamed bodies without Content-Length", async () => {
  globalThis.fetch = async () => { throw new Error("must not call upstream"); };
  let pulls = 0;
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) { pulls++; controller.enqueue(new Uint8Array(1024 * 1024)); },
    cancel() { cancelled = true; },
  });
  const init: RequestInit & { duplex: "half" } = { method: "POST", body, duplex: "half" };
  const response = await proxyRequest(new Request("http://local", init), ["device-models", "00000000-0000-0000-0000-000000000001", "reference-images"]);
  assert.equal(response.status, 413);
  assert.equal(cancelled, true);
  assert.ok(pulls < 12);
});
test("proxy rejects oversized request bodies", async () => {
  assert.equal((await proxyRequest(new Request("http://local", {
    method: "POST", body: "x".repeat(17000),
  }), ["auth", "login"])).status, 413);
});

test("proxy stops an oversized streamed body before buffering it all", async () => {
  let cancelled = false;
  let pulls = 0;
  globalThis.fetch = async () => { throw new Error("must not call upstream"); };
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      pulls++;
      if (pulls <= 32) controller.enqueue(new Uint8Array(8192));
      else controller.close();
    },
    cancel() { cancelled = true; },
  });
  const init: RequestInit & { duplex: "half" } = { method: "POST", body, duplex: "half" };
  const response = await proxyRequest(new Request("http://local", init), ["auth", "login"]);
  assert.equal(response.status, 413);
  assert.equal(cancelled, true);
  assert.ok(pulls < 32);
});

test("all locally generated proxy errors are private and nosniff", async () => {
  globalThis.fetch = async () => { throw new Error("unavailable"); };
  const cases: [Request, string[], number][] = [
    [new Request("http://local"), ["not-allowed"], 404],
    [new Request("http://local", { method: "DELETE" }), ["device-models"], 405],
    [new Request("http://local", { method: "POST", body: "x".repeat(17000) }), ["device-models"], 413],
    [new Request("http://local"), ["device-models"], 503],
    [new Request("http://local", {
      method: "POST", duplex: "half", body: new ReadableStream({
        start(controller) { controller.error(new Error("broken stream")); },
      }),
    } as RequestInit & { duplex: "half" }), ["device-models"], 400],
  ];
  for (const [request, path, status] of cases) {
    const response = await proxyRequest(request, path);
    assert.equal(response.status, status);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.equal(response.headers.get("x-content-type-options"), "nosniff");
    assert.equal(typeof (await response.json()).detail, "string");
  }
});
