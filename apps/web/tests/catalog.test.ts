import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { CatalogError, canManage, catalogMutation, catalogOptions, catalogRequest, modelQuery, validatePhoto } from "../lib/catalog";
import { modelPayload, newDraft } from "../lib/catalog-form";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const draft = () => ({ ...newDraft(), model_name: " AP  680-L ", category_id: "cat", manufacturer_id: "maker" });

test("model payload normalizes names and aliases; typed specifications roundtrip without loss", () => {
  const value = draft(); value.aliases = " Outdoor   AP \n AP680 \n";
  const result = modelPayload(value);
  assert.equal(result.model_name, "AP 680-L"); assert.deepEqual(result.aliases, ["Outdoor AP", "AP680"]);
  const specs = { ports: 4, poe: true, note: "original", missing: null, values: ["a", 2, false, null], constructor: "valid key" };
  const model = { ...result, specs, id: "model", version: 7, created_at: "", updated_at: "" };
  const roundtrip = modelPayload(newDraft(model), model);
  assert.deepEqual({ ...roundtrip.specs }, specs); assert.equal(roundtrip.version, 7);
});

test("model validation rejects blank names, duplicate aliases, invalid numbers/keys/nesting size", () => {
  assert.throws(() => modelPayload({ ...draft(), model_name: "  " }));
  assert.throws(() => modelPayload({ ...draft(), category_id: "" }));
  assert.throws(() => modelPayload({ ...draft(), aliases: "AP\nap " }), /berulang/);
  for (const value of ["", "Infinity", "1000000000001", "NaN"]) assert.throws(() => modelPayload({ ...draft(), specs: [{ key: "ports", kind: "number", value, items: [] }] }));
  assert.throws(() => modelPayload({ ...draft(), specs: [{ key: "bad key", kind: "text", value: "x", items: [] }] }));
  assert.throws(() => modelPayload({ ...draft(), specs: Array.from({ length: 33 }, (_, index) => ({ key: String(index), kind: "text", value: "", items: [] })) }));
  assert.throws(() => modelPayload({ ...draft(), specs: [{ key: "large", kind: "list", value: "", items: Array.from({ length: 20 }, () => ({ kind: "text", value: "a".repeat(500) })) }] }), /panjang/);
});

test("filters use encoded literal search and resettable numbered pages", () => {
  const path = modelQuery({ search: "AP & outdoor%", category: "cat", manufacturer: "maker", status: "false", page: 3 });
  const query = new URL("http://local" + path).searchParams;
  assert.equal(query.get("search"), "AP & outdoor%"); assert.equal(query.get("page"), "3");
  assert.equal(query.get("is_active"), "false"); assert.equal(query.get("category_id"), "cat");
  assert.ok(!modelQuery({ search: "", category: "", manufacturer: "", status: "all", page: 1 }).includes("is_active"));
});

test("catalog mutations use session CSRF and never expose or store JWT", async () => {
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return Response.json(calls.length === 1 ? { csrf_token: "session-csrf" } : { id: "new" }, { status: calls.length === 1 ? 200 : 201 }); };
  await catalogMutation("/device-models", "POST", { model_name: "AP" });
  assert.equal(calls[0].url, "/api/v1/auth/session"); assert.equal(calls[1].init?.credentials, "same-origin");
  assert.equal(new Headers(calls[1].init?.headers).get("x-csrf-token"), "session-csrf");
  assert.equal(new Headers(calls[1].init?.headers).get("authorization"), null);
  assert.equal(calls[1].init?.body, '{"model_name":"AP"}');
});

test("expired session prevents a write; 409 conflict is identified and does not auto-retry", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ detail: "Authentication required" }, { status: 401 }); };
  await assert.rejects(catalogMutation("/device-models", "POST", {}), (error: unknown) => error instanceof CatalogError && error.status === 401);
  assert.equal(calls, 1);
  globalThis.fetch = async () => { calls++; return Response.json({ detail: "Catalog record changed; reload and retry" }, { status: 409 }); };
  await assert.rejects(catalogRequest("/device-models/id"), (error: unknown) => error instanceof CatalogError && error.conflict);
  assert.equal(calls, 2);
});

test("master options read all pages including archived references", async () => {
  let calls = 0;
  globalThis.fetch = async () => Response.json({ items: [{ id: ++calls, is_active: calls === 1 }], total_pages: 2 });
  const options = await catalogOptions<{ id: number; is_active: boolean }>("manufacturers");
  assert.deepEqual(options.map(item => item.id), [1, 2]); assert.equal(options[1].is_active, false);
});

test("photo preflight and role checks are narrow while backend remains authoritative", () => {
  assert.equal(canManage("ADMIN"), true); assert.equal(canManage("VIEWER"), false); assert.equal(canManage("OFFICER"), false);
  validatePhoto({ size: 100, type: "image/webp" });
  assert.throws(() => validatePhoto({ size: 0, type: "image/png" }));
  assert.throws(() => validatePhoto({ size: 9 * 1024 * 1024, type: "image/png" }));
  assert.throws(() => validatePhoto({ size: 100, type: "image/svg+xml" }));
});
