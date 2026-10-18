import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { JSDOM } from "jsdom";
import { act, type ReactNode } from "react";
import { CatalogRole } from "../components/catalog/shared";
import AssetList from "../components/assets/asset-list";
import AssetForm from "../components/assets/asset-form";
import AssetDetail from "../components/assets/asset-detail";
import Identifiers from "../components/assets/identifiers";
import CsvImport from "../components/assets/csv-import";
import NewAsset from "../components/assets/new-asset";
import { assetDraft, assetPayload, assetQuery, readCsv, validateIdentifier, type Asset, type Identifier, type Preview } from "../lib/assets";
import type { Role } from "../lib/catalog";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
const win = dom.window;
Object.assign(globalThis, { window: win, document: win.document, HTMLElement: win.HTMLElement, HTMLInputElement: win.HTMLInputElement, HTMLSelectElement: win.HTMLSelectElement, HTMLTextAreaElement: win.HTMLTextAreaElement, Event: win.Event, MouseEvent: win.MouseEvent, FormData: win.FormData, IS_REACT_ACT_ENVIRONMENT: true });
Object.defineProperty(globalThis, "navigator", { value: win.navigator, configurable: true });
Object.defineProperty(win.HTMLDialogElement.prototype, "showModal", { value: function () { this.setAttribute("open", ""); } });
Object.defineProperty(win.HTMLDialogElement.prototype, "close", { value: function () { this.removeAttribute("open"); } });
const reactDomClient = import("react-dom/client");
let container: HTMLDivElement;
let root: import("react-dom/client").Root;
const originalFetch = globalThis.fetch;
const asset: Asset = { id: "00000000-0000-0000-0000-000000000001", asset_code: "SYNTHETIC-001", device_model_id: "00000000-0000-0000-0000-000000000002", lifecycle_status: "IN_STOCK", condition: "UNKNOWN", notes: null, purchase_date: null, installed_at: null, created_at: "2026-10-19T00:00:00Z", updated_at: "2026-10-19T00:00:00Z", version: 7 };
const model = { id: asset.device_model_id, model_name: "Synthetic AP", manufacturer_id: "maker", is_active: true };
const claim: Identifier = { id: "claim", asset_id: asset.id, identifier_type: "MAC_WLAN", raw_value: "aabb.ccdd.eeff", normalized_value: "AA:BB:CC:DD:EE:FF", source: "IMPORT", verification_status: "UNVERIFIED", notes: null, version: 3, collision_asset_ids: ["other-unit"] };
const csv = "asset_code,manufacturer,model\nSYNTHETIC-001,Synthetic Maker,Synthetic AP";
const preview: Preview = { total_rows: 1, valid_rows: 1, invalid_rows: 0, has_collisions: false, rows: [{ row: 2, asset_code: asset.asset_code, valid: true, errors: [], collisions: [], location_hint: "Staging only", asset_id: null, version: null }] };
const page = (items: unknown[], total = items.length, number = 1) => ({ items, total, page: number, page_size: 15, total_pages: Math.ceil(total / 15) });
type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;
function mock(handler: Handler, archived = false) {
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    if (path === "/api/v1/auth/session") return Response.json({ csrf_token: "session-csrf" });
    if (path.startsWith("/api/v1/device-models?")) return Response.json(page([{ ...model, is_active: !archived }]));
    if (path.startsWith("/api/v1/manufacturers?")) return Response.json(page([{ id: "maker", name: "Synthetic Maker" }]));
    return handler(path, init);
  };
}
async function settle() { await act(async () => { await new Promise(resolve => setTimeout(resolve, 5)); }); }
async function render(node: ReactNode, role: Role = "ADMIN") { await act(async () => root.render(<CatalogRole value={role}>{node}</CatalogRole>)); await settle(); }
async function click(element: Element) { await act(async () => { (element as HTMLElement).click(); }); await settle(); }
function button(text: string) { const found = Array.from(container.querySelectorAll("button")).find(element => element.textContent?.trim() === text); assert.ok(found, `Missing button ${text}`); return found; }
function input(label: string) { const field = Array.from(container.querySelectorAll("label")).find(element => element.textContent?.trim().startsWith(label))?.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input,select,textarea"); assert.ok(field, `Missing input ${label}`); return field; }
async function change(field: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string) {
  const prototype = field instanceof win.HTMLSelectElement ? win.HTMLSelectElement.prototype : field instanceof win.HTMLTextAreaElement ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(field, value); field.dispatchEvent(new win.Event("input", { bubbles: true })); field.dispatchEvent(new win.Event("change", { bubbles: true })); });
}
async function submit(form: Element) { await act(async () => { form.dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true })); }); await settle(); }
async function upload(text = csv, size = new TextEncoder().encode(text).length) {
  const file = { name: "synthetic.csv", size, arrayBuffer: async () => new TextEncoder().encode(text).buffer };
  Object.defineProperty(input("Pilih CSV"), "files", { configurable: true, value: [file] });
  await act(async () => input("Pilih CSV").dispatchEvent(new win.Event("change", { bubbles: true }))); await settle();
}
beforeEach(async () => { const { createRoot } = await reactDomClient; container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); globalThis.fetch = originalFetch; });

test("asset payload preserves immutable code, optional empty dates and timezone validation", () => {
  const draft = assetDraft(asset);
  draft.asset_code = "FORGED";
  const payload = assetPayload(draft, asset);
  assert.ok(!("asset_code" in payload)); assert.equal(payload.version, 7); assert.equal(payload.purchase_date, null);
  const created = assetPayload({ ...draft, asset_code: " test-001 " });
  assert.equal("asset_code" in created && created.asset_code, "TEST-001");
  assert.throws(() => assetPayload({ ...draft, asset_code: "bad space" }), /Asset ID/);
  assert.throws(() => assetPayload({ ...draft, installed_at: "2026-10-19T08:00:00" }, asset), /zona waktu/);
  assert.equal(assetPayload({ ...draft, installed_at: "2026-10-19T08:00:00+08:00" }, asset).installed_at, "2026-10-19T08:00:00+08:00");
  assert.throws(() => validateIdentifier("SERIAL_NUMBER", "UNKNOWN"), /SN palsu/);
  assert.throws(() => validateIdentifier("MAC_LAN", "AA:BB-CC:DD:EE:FF"), /MAC/);
  validateIdentifier("MAC_WLAN", "aabb.ccdd.eeff");
});

test("file preflight enforces bytes and rejects invalid UTF-8", async () => {
  await assert.rejects(readCsv({ size: 262145, arrayBuffer: async () => new ArrayBuffer(0) }), /256 KiB/);
  await assert.rejects(readCsv({ size: 1, arrayBuffer: async () => Uint8Array.of(255).buffer }), /UTF-8/);
  assert.equal(await readCsv({ size: 3, arrayBuffer: async () => new TextEncoder().encode("a,b").buffer }), "a,b");
  assert.ok(!assetQuery({ search: "x", model: "m", status: "IN_USE", page: 3 }, true).includes("page="));
});

test("list read-only roles hide all write/import/export controls", async () => {
  mock(() => Response.json(page([asset])));
  for (const role of ["OFFICER", "VIEWER"] as Role[]) {
    await render(<AssetList />, role);
    assert.match(container.textContent!, /SYNTHETIC-001/); assert.match(container.textContent!, /Synthetic Maker/);
    assert.ok(!container.querySelector('a[href="/assets/new"]')); assert.ok(!container.querySelector('a[href="/assets/import"]'));
    assert.ok(!container.querySelector('a[href*="export.csv"]'));
  }
  await render(<AssetList />); assert.ok(container.querySelector('a[href="/assets/new"]'));
});

test("list search/model/status filter and pagination reset then export uses same filters", async () => {
  const reads: string[] = [];
  mock(url => { reads.push(url); return Response.json(page([asset], 31, Number(new URL(url, "http://local").searchParams.get("page")) || 1)); });
  await render(<AssetList />); await click(button("Berikutnya"));
  assert.match(reads.at(-1)!, /page=2/);
  await change(input("Cari Asset"), "aabbccddeeff"); await change(input("Model"), model.id); await change(input("Status"), "IN_USE");
  await submit(container.querySelector("form")!);
  const query = new URL(reads.at(-1)!, "http://local").searchParams;
  assert.equal(query.get("page"), "1"); assert.equal(query.get("search"), "aabbccddeeff"); assert.equal(query.get("model_id"), model.id); assert.equal(query.get("status"), "IN_USE");
  const link = container.querySelector('a[href*="export.csv"]')!;
  assert.match(link.getAttribute("href")!, /search=aabbccddeeff/); assert.ok(!link.getAttribute("href")!.includes("page="));
});

test("list loading, empty and expired session show recovery states", async () => {
  let resolve!: (value: Response) => void;
  mock(() => new Promise<Response>(done => { resolve = done; }));
  await render(<AssetList />); assert.match(container.textContent!, /Memuat aset/);
  await act(async () => resolve(Response.json(page([])))); await settle(); assert.match(container.textContent!, /Belum ada aset/);
  mock(() => Response.json({ detail: "expired" }, { status: 401 }));
  await change(input("Cari Asset"), "expired"); await submit(container.querySelector("form")!);
  assert.ok(container.querySelector('a[href="/login"]'));
});

test("create unit without fake SN sends CSRF and shows saved link without retry", async () => {
  const writes: RequestInit[] = [];
  mock((_url, init) => { writes.push(init); return Response.json(asset, { status: 201 }); });
  await render(<NewAsset />); await change(input("Asset ID"), " synthetic-001 "); await change(input("Model perangkat"), model.id);
  await submit(container.querySelector("form")!);
  assert.equal(writes.length, 1); assert.equal((writes[0].headers as Record<string, string>)["X-CSRF-Token"], "session-csrf");
  const body = JSON.parse(String(writes[0].body)); assert.equal(body.asset_code, asset.asset_code); assert.ok(!("serial_number" in body));
  assert.ok(container.querySelector(`a[href="/assets/${asset.id}"]`)); assert.equal(container.querySelector("form"), null);
});

test("edit freezes version across background changes and keeps draft after stale conflict", async () => {
  let body: Record<string, unknown> = {};
  mock((_url, init) => { body = JSON.parse(String(init.body)); return Response.json({ detail: "Asset metadata changed; reload" }, { status: 409 }); }, true);
  await render(<AssetForm initial={asset} onSaved={() => assert.fail("must not save")} />);
  assert.ok((input("Asset ID") as HTMLInputElement).disabled); assert.match(container.textContent!, /arsip/);
  await change(input("Catatan"), "Keep my draft");
  await render(<AssetForm initial={{ ...asset, version: 99 }} onSaved={() => assert.fail("must not save")} />);
  await submit(container.querySelector("form")!);
  assert.equal(body.version, 7); assert.ok(!("asset_code" in body)); assert.equal(input("Catatan").value, "Keep my draft");
  assert.match(container.textContent!, /Data telah berubah/); assert.ok(button("Simpan aset").disabled);
});

test("detail renders missing SN and audit snapshots without writes for VIEWER", async () => {
  mock((url, init) => { assert.ok(!init.method); return Response.json(url.endsWith("/identifiers") ? [] : url.includes("/events?") ? page([{ id: "event", actor_id: "synthetic-actor", event_type: "UPDATE", recorded_at: "2026-10-19", before_json: { notes: "Before" }, after_json: { notes: "After" } }]) : asset); });
  await render(<AssetDetail id={asset.id} />, "VIEWER");
  assert.match(container.textContent!, /SN tidak tersedia \/ label rusak/); assert.match(container.textContent!, /Before/); assert.match(container.textContent!, /After/);
  assert.ok(!Array.from(container.querySelectorAll("button")).some(element => /Edit aset|Tambah identifier|Arsipkan aset/.test(element.textContent!)));
});

test("archive requires confirmation and sends current asset version", async () => {
  let writes = 0;
  mock((url, init) => {
    if (init.method === "POST") { writes++; assert.equal(JSON.parse(String(init.body)).version, 7); return Response.json({ ...asset, lifecycle_status: "ARCHIVED", version: 8 }); }
    return Response.json(url.endsWith("/identifiers") ? [] : url.includes("/events?") ? page([]) : { ...asset, lifecycle_status: writes ? "ARCHIVED" : "IN_STOCK" });
  });
  await render(<AssetDetail id={asset.id} />); await click(button("Arsipkan aset")); assert.equal(writes, 0);
  await click(button("Batalkan")); assert.equal(writes, 0); await click(button("Arsipkan aset")); await click(button("Ya, lanjutkan")); assert.equal(writes, 1);
  assert.match(container.textContent!, /Unit diarsipkan/);
});

test("identifier editing sends parent and claim versions, source and verification", async () => {
  let body: Record<string, unknown> = {}; let done = false;
  mock((_url, init) => { body = JSON.parse(String(init.body)); return Response.json({ identifier: claim, asset_version: 8 }); });
  await render(<Identifiers asset={asset} items={[claim]} editable onChanged={() => { done = true; }} onEditing={() => undefined} />);
  assert.match(container.textContent!, /Benturan klaim/); assert.ok(container.querySelector('a[href="/assets/other-unit"]'));
  await click(button("Edit identifier")); await change(input("Verifikasi"), "VERIFIED"); await submit(container.querySelector("form")!);
  assert.equal(body.asset_version, 7); assert.equal(body.version, 3); assert.equal(body.source, "IMPORT"); assert.equal(body.verification_status, "VERIFIED"); assert.ok(done);
});

test("identifier rejects placeholder SN without a write and preserves raw evidence", async () => {
  let writes = 0;
  mock(() => { writes++; return Response.json({}); });
  await render(<Identifiers asset={asset} items={[]} editable onChanged={() => undefined} onEditing={() => undefined} />);
  await click(button("Tambah identifier")); await change(input("Nilai bukti"), "UNKNOWN"); await submit(container.querySelector("form")!);
  assert.equal(writes, 0); assert.match(container.textContent!, /SN palsu/); assert.equal(input("Nilai bukti").value, "UNKNOWN");
});

test("soft delete confirmation sends both versions", async () => {
  let target = "";
  mock((url, init) => { assert.equal(init.method, "DELETE"); target = url; return Response.json({ identifier: claim, asset_version: 8 }); });
  await render(<Identifiers asset={asset} items={[claim]} editable onChanged={() => undefined} onEditing={() => undefined} />);
  await click(button("Hapus identifier")); assert.equal(target, ""); await click(button("Ya, lanjutkan"));
  assert.match(target, /version=3&asset_version=7/);
});

test("CSV invalid preview shows row errors, staging and prevents confirmation", async () => {
  let commits = 0;
  mock((url) => { if (url.endsWith("/commit")) commits++; return Response.json({ ...preview, valid_rows: 0, invalid_rows: 1, rows: [{ ...preview.rows[0], valid: false, errors: ["Unknown model", "Duplicate asset code"] }] }); });
  await render(<CsvImport />); await upload(); await submit(container.querySelector("form")!);
  assert.match(container.textContent!, /Unknown model/); assert.match(container.textContent!, /Duplicate asset code/); assert.match(container.textContent!, /Staging only/); assert.ok(button("Konfirmasi impor").disabled); assert.equal(commits, 0);
});

test("CSV collision acknowledgement and confirm then successful summary", async () => {
  let payload: Record<string, unknown> = {};
  mock((url, init) => {
    if (url.endsWith("/preview")) return Response.json({ ...preview, has_collisions: true, rows: [{ ...preview.rows[0], collisions: [{ identifier_type: "MAC_LAN", normalized_value: "AA:BB:CC:DD:EE:FF", asset_ids: ["other"], csv_rows: [3] }] }] });
    payload = JSON.parse(String(init.body)); return Response.json({ import_id: payload.idempotency_key, status: "COMMITTED", created_count: 1, failed_count: 0, rows: [{ ...preview.rows[0], asset_id: asset.id }], errors: [] });
  });
  await render(<CsvImport />); await upload(); await submit(container.querySelector("form")!);
  assert.ok(button("Konfirmasi impor").disabled); await click(input("Saya telah meninjau")); await click(button("Konfirmasi impor")); assert.deepEqual(payload, {});
  await click(button("Ya, lanjutkan")); assert.equal(payload.allow_identifier_collisions, true); assert.equal(payload.csv_text, csv); assert.match(String(payload.idempotency_key), /^[0-9a-f-]{36}$/);
  assert.match(container.textContent!, /Impor berhasil/); assert.ok(container.querySelector(`a[href="/assets/${asset.id}"]`));
});

test("CSV uncertain commit retry keeps exact key, payload and collision flag", async () => {
  const bodies: string[] = [];
  mock((url, init) => {
    if (url.endsWith("/preview")) return Response.json(preview);
    bodies.push(String(init.body)); if (bodies.length === 1) throw new Error("Synthetic network loss after commit");
    return Response.json({ import_id: JSON.parse(bodies[0]).idempotency_key, status: "COMMITTED", created_count: 1, failed_count: 0, rows: preview.rows, errors: [] });
  });
  await render(<CsvImport />); await upload(); await submit(container.querySelector("form")!); await click(button("Konfirmasi impor")); await click(button("Ya, lanjutkan"));
  assert.ok(input("Pilih CSV").disabled); assert.match(container.textContent!, /Hasil commit belum diketahui/);
  const leaving = new win.Event("beforeunload", { cancelable: true });
  win.dispatchEvent(leaving); assert.ok(leaving.defaultPrevented);
  await click(button("Coba ulang commit yang sama")); assert.equal(bodies.length, 2); assert.equal(bodies[1], bodies[0]); assert.match(container.textContent!, /Impor berhasil/);
  const completed = new win.Event("beforeunload", { cancelable: true });
  win.dispatchEvent(completed); assert.equal(completed.defaultPrevented, false);
});

test("missing UUID support releases import lock without sending commit", async () => {
  let writes = 0;
  mock(url => { if (url.endsWith("/commit")) writes++; return Response.json(preview); });
  await render(<CsvImport />); await upload(); await submit(container.querySelector("form")!);
  const original = crypto.randomUUID;
  Object.defineProperty(crypto, "randomUUID", { configurable: true, value: undefined });
  try {
    await click(button("Konfirmasi impor")); await click(button("Ya, lanjutkan"));
    assert.match(container.textContent!, /kunci impor aman/); assert.equal(writes, 0);
    assert.equal(button("Konfirmasi impor").disabled, false);
  } finally { Object.defineProperty(crypto, "randomUUID", { configurable: true, value: original }); }
});

test("unreadable success response never reports saved or retries non-idempotent create", async () => {
  let writes = 0;
  mock(() => { writes++; return new Response("<html>bad gateway response</html>", { status: 200 }); });
  await render(<NewAsset />); await change(input("Asset ID"), "SYNTHETIC-001"); await change(input("Model perangkat"), model.id);
  await submit(container.querySelector("form")!);
  assert.equal(writes, 1); assert.match(container.textContent!, /hasil belum diketahui/);
  assert.equal(button("Simpan aset").disabled, true);
  assert.ok(!container.querySelector(`a[href="/assets/${asset.id}"]`));
});

test("CSV REJECTED 409 renders batch errors and allows fresh preview", async () => {
  mock(url => url.endsWith("/preview") ? Response.json(preview) : Response.json({ status: "REJECTED", import_id: "key", created_count: 0, failed_count: 1, rows: [{ ...preview.rows[0], errors: ["Asset code now exists"] }], errors: ["Batch conflict"] }, { status: 409 }));
  await render(<CsvImport />); await upload(); await submit(container.querySelector("form")!); await click(button("Konfirmasi impor")); await click(button("Ya, lanjutkan"));
  assert.match(container.textContent!, /Batch ditolak/); assert.match(container.textContent!, /Batch conflict/); assert.match(container.textContent!, /Asset code now exists/); assert.equal(input("Pilih CSV").disabled, false);
  await submit(container.querySelector("form")!); assert.ok(button("Konfirmasi impor"));
});

test("changing CSV invalidates preview and acknowledgement; oversize never uploads", async () => {
  let requests = 0;
  mock(() => { requests++; return Response.json(preview); });
  await render(<CsvImport />); await upload(); await submit(container.querySelector("form")!); assert.ok(button("Konfirmasi impor"));
  await upload(csv + "\n"); assert.ok(!Array.from(container.querySelectorAll("button")).some(item => item.textContent === "Konfirmasi impor"));
  await upload(csv, 262145); assert.match(container.textContent!, /256 KiB/); assert.ok(button("Periksa preview").disabled); assert.equal(requests, 1);
});
