import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { proxyRequest } from "../lib/proxy";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

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
