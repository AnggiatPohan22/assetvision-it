import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { JSDOM } from "jsdom";
import { act, type ReactNode } from "react";
import { CatalogRole } from "../components/catalog/shared";
import ModelList from "../components/catalog/model-list";
import ModelForm from "../components/catalog/model-form";
import ModelDetail from "../components/catalog/model-detail";
import MasterManager from "../components/catalog/master-manager";
import Gallery from "../components/catalog/gallery";
import type { DeviceModel, Role } from "../lib/catalog";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
const win = dom.window;
Object.assign(globalThis, { window: win, document: win.document, HTMLElement: win.HTMLElement, HTMLInputElement: win.HTMLInputElement,
  HTMLSelectElement: win.HTMLSelectElement, HTMLTextAreaElement: win.HTMLTextAreaElement, Event: win.Event, MouseEvent: win.MouseEvent,
  FormData: win.FormData, File: win.File, IS_REACT_ACT_ENVIRONMENT: true });
Object.defineProperty(globalThis, "navigator", { value: win.navigator, configurable: true });
Object.defineProperty(win.HTMLDialogElement.prototype, "showModal", { value: function () { this.setAttribute("open", ""); } });
Object.defineProperty(win.HTMLDialogElement.prototype, "close", { value: function () { this.removeAttribute("open"); } });
const reactDomClient = import("react-dom/client");
let container: HTMLDivElement;
let root: import("react-dom/client").Root;
const originalFetch = globalThis.fetch;
const model: DeviceModel = { id: "00000000-0000-0000-0000-000000000001", model_name: "AP680-L", manufacturer_id: "maker", category_id: "cat", aliases: ["Outdoor AP"], description: "Synthetic reference", environment: "outdoor", specs: { ports: 4 }, is_active: true, version: 1, created_at: "", updated_at: "" };
const category = { id: "cat", name: "Access Point", code: "access-point", is_active: true, version: 1 };
const maker = { id: "maker", name: "Ruijie", website: null, is_active: true, version: 1 };
const page = (items: unknown[], total = items.length, pageNumber = 1) => ({ items, total, page: pageNumber, page_size: 15, total_pages: Math.ceil(total / 15) });
type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;
function mock(handler: Handler) {
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    if (path.startsWith("/api/v1/device-categories") && (!init.method || init.method === "GET")) return Response.json(page([category]));
    if (path.startsWith("/api/v1/manufacturers") && (!init.method || init.method === "GET")) return Response.json(page([maker]));
    if (path === "/api/v1/auth/session") return Response.json({ csrf_token: "session-csrf" });
    return handler(path, init);
  };
}
async function settle() { await act(async () => { await new Promise(resolve => setTimeout(resolve, 5)); }); }
async function render(node: ReactNode, role: Role = "ADMIN") { await act(async () => root.render(<CatalogRole value={role}>{node}</CatalogRole>)); await settle(); }
async function click(button: Element) { await act(async () => { (button as HTMLElement).click(); }); await settle(); }
function button(text: string) { const found = Array.from(container.querySelectorAll("button")).find(element => element.textContent?.trim() === text); assert.ok(found, `Missing button ${text}`); return found; }
function input(label: string) { const field = Array.from(container.querySelectorAll("label")).find(element => element.textContent?.trim().startsWith(label))?.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input,select,textarea"); assert.ok(field, `Missing input ${label}`); return field; }
async function change(field: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string) {
  const prototype = field instanceof win.HTMLSelectElement ? win.HTMLSelectElement.prototype : field instanceof win.HTMLTextAreaElement ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(field, value); field.dispatchEvent(new win.Event("input", { bubbles: true })); field.dispatchEvent(new win.Event("change", { bubbles: true })); });
}
async function submit(form: Element) { await act(async () => { form.dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true })); }); await settle(); }
beforeEach(async () => { const { createRoot } = await reactDomClient; container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); globalThis.fetch = originalFetch; });

test("model list renders read-only roles and ADMIN create control", async () => {
  mock(() => Response.json(page([model])));
  await render(<ModelList />, "VIEWER");
  assert.match(container.textContent!, /AP680-L/); assert.match(container.textContent!, /Ruijie/);
  assert.ok(!container.querySelector('a[href="/catalog/models/new"]'));
  await render(<ModelList />, "ADMIN"); assert.ok(container.querySelector('a[href="/catalog/models/new"]'));
});

test("filter/search and pagination send encoded filters, returning to page one", async () => {
  const calls: string[] = [];
  mock(url => { calls.push(url); const query = new URL("http://local" + url).searchParams; return Response.json(page([model], 31, Number(query.get("page")))); });
  await render(<ModelList />); await click(button("Berikutnya"));
  assert.ok(calls.at(-1)?.includes("page=2"));
  await change(input("Cari model"), "AP & outdoor"); await change(input("Status"), "false"); await submit(container.querySelector("form")!);
  const query = new URL("http://local" + calls.at(-1)).searchParams;
  assert.equal(query.get("page"), "1"); assert.equal(query.get("search"), "AP & outdoor"); assert.equal(query.get("is_active"), "false");
});

test("loading, failure/retry, and empty results are visible and accessible", async () => {
  let retry = false;
  mock(() => retry ? Response.json(page([])) : Response.json({ detail: "unavailable" }, { status: 503 }));
  await render(<ModelList />); assert.ok(container.querySelector('[role="alert"]'));
  retry = true; await click(button("Coba muat lagi")); assert.match(container.textContent!, /Belum ada model yang sesuai/);
});

test("create model validates, sends normalized payload, and invokes saved callback", async () => {
  let payload: Record<string, unknown> | undefined;
  let saved = false;
  mock((_url, init) => { payload = JSON.parse(String(init.body)); return Response.json(model, { status: 201 }); });
  await render(<ModelForm onSaved={() => { saved = true; }} />);
  await change(input("Nama model"), " AP  680-L "); await change(input("Kategori"), "cat"); await change(input("Produsen"), "maker");
  await submit(container.querySelector("form")!);
  assert.equal(saved, true); assert.equal(payload?.model_name, "AP 680-L"); assert.equal(payload?.manufacturer_id, "maker");
});

test("edit conflict preserves draft and original version without automatic resubmission", async () => {
  const writes: Record<string, unknown>[] = [];
  mock((_url, init) => { writes.push(JSON.parse(String(init.body))); return Response.json({ detail: "Catalog record changed; reload and retry" }, { status: 409 }); });
  await render(<ModelForm initial={model} onSaved={() => assert.fail("must not save")} onReload={() => undefined} />);
  await change(input("Nama model"), "Unsaved draft"); await submit(container.querySelector("form")!);
  assert.equal(input("Nama model").value, "Unsaved draft"); assert.equal(writes[0].version, 1); assert.equal(writes.length, 1);
  assert.match(container.querySelector('[role="alert"]')!.textContent!, /Isian Anda tetap ada/);
});

test("background model refresh cannot advance a draft's optimistic version", async () => {
  const versions: unknown[] = [];
  mock((_url, init) => { versions.push(JSON.parse(String(init.body)).version); return Response.json({ detail: "Catalog record changed; reload and retry" }, { status: 409 }); });
  await render(<ModelForm initial={model} onSaved={() => undefined} />);
  await change(input("Nama model"), "Draft from version one");
  await render(<ModelForm initial={{ ...model, version: 2, model_name: "Another admin change" }} onSaved={() => undefined} />);
  await submit(container.querySelector("form")!);
  assert.deepEqual(versions, [1]); assert.equal(input("Nama model").value, "Draft from version one");
});

test("read-only model form and master management cannot initiate writes", async () => {
  let writes = 0;
  mock((_url, init) => { if (init.method) writes++; return Response.json({}); });
  await render(<ModelForm onSaved={() => undefined} />, "OFFICER"); assert.equal(container.querySelector("form"), null);
  await render(<MasterManager />, "VIEWER"); assert.equal(container.querySelector("form"), null); assert.equal(writes, 0);
});

test("master category create and edit use existing version and retain conflict fields", async () => {
  const writes: Record<string, unknown>[] = [];
  mock((_url, init) => { writes.push(JSON.parse(String(init.body))); return Response.json({ detail: "Catalog record changed; reload and retry" }, { status: 409 }); });
  await render(<MasterManager />);
  await click(container.querySelector('button[aria-label="Edit Access Point"]')!);
  await change(input("Nama kategori"), "Edited category");
  await submit(container.querySelector('form[aria-label="Form kategori"]')!);
  assert.equal(writes[0].version, 1); assert.equal(input("Nama kategori").value, "Edited category");
});

test("read-only detail includes protected gallery but no mutation controls", async () => {
  mock(url => Response.json(url.includes("reference-images") ? { items: [], model_version: 1 } : model));
  await render(<ModelDetail id={model.id} />, "VIEWER");
  assert.match(container.textContent!, /Foto referensi/); assert.match(container.textContent!, /AP680-L/);
  assert.ok(!Array.from(container.querySelectorAll("button")).some(value => /Edit model|Arsipkan|Unggah/.test(value.textContent!)));
});

test("archive confirmation can cancel then sends current model version", async () => {
  let archived = false; let version: unknown;
  mock((url, init) => {
    if (init.method === "POST") { archived = true; version = JSON.parse(String(init.body)).version; return Response.json({ ...model, version: 2, is_active: false }); }
    return Response.json(url.includes("reference-images") ? { items: [], model_version: archived ? 2 : 1 } : { ...model, is_active: !archived, version: archived ? 2 : 1 });
  });
  await render(<ModelDetail id={model.id} />); await click(button("Arsipkan model"));
  assert.ok(container.querySelector("dialog[open]")); await click(button("Batalkan")); assert.equal(archived, false);
  await click(button("Arsipkan model")); await click(button("Ya, lanjutkan"));
  assert.equal(version, 1); assert.match(container.textContent!, /Pulihkan model/);
});

test("gallery uploads multiple files sequentially with updated versions", async () => {
  const versions: string[] = [];
  mock((_url, init) => {
    if (init.method === "POST") { const form = init.body as FormData; versions.push(String(form.get("version"))); return Response.json({ image: { id: String(versions.length) }, model_version: versions.length + 1 }, { status: 201 }); }
    return Response.json({ items: [], model_version: versions.length + 1 });
  });
  await render(<Gallery model={model} editable onChanged={() => undefined} onBusy={() => undefined} />);
  Object.defineProperty(input("Pilih foto"), "files", { configurable: true, value: [new File(["one"], "one.png", { type: "image/png" }), new File(["two"], "two.webp", { type: "image/webp" })] });
  await submit(container.querySelector("form")!); await settle();
  assert.deepEqual(versions, ["1", "2"]); assert.match(container.textContent!, /2 foto berhasil diunggah/);
});

test("gallery keeps partial failure visible and never retries completed uploads", async () => {
  let writes = 0;
  mock((_url, init) => init.method === "POST"
    ? (++writes === 1 ? Response.json({ image: { id: "one" }, model_version: 2 }, { status: 201 }) : Response.json({ detail: "bad image" }, { status: 415 }))
    : Response.json({ items: [], model_version: 1 + Math.min(1, writes) }));
  await render(<Gallery model={model} editable onChanged={() => undefined} onBusy={() => undefined} />);
  Object.defineProperty(input("Pilih foto"), "files", { configurable: true, value: [new File(["one"], "one.png", { type: "image/png" }), new File(["two"], "two.png", { type: "image/png" })] });
  await submit(container.querySelector("form")!); await settle();
  assert.equal(writes, 2); assert.match(container.textContent!, /1 foto sudah berhasil/); assert.ok(container.querySelector('[role="alert"]'));
});

test("invalid photo preflight prevents network writes", async () => {
  let writes = 0;
  mock((_url, init) => { if (init.method) writes++; return Response.json({ items: [], model_version: 1 }); });
  await render(<Gallery model={model} editable onChanged={() => undefined} onBusy={() => undefined} />);
  Object.defineProperty(input("Pilih foto"), "files", { configurable: true, value: [new File(["svg"], "bad.svg", { type: "image/svg+xml" })] });
  await submit(container.querySelector("form")!); assert.equal(writes, 0); assert.match(container.textContent!, /JPEG, PNG, atau WebP/);
});

test("pending reads show a loading status before an empty state", async () => {
  let resolve!: (value: Response) => void;
  mock(() => new Promise<Response>(done => { resolve = done; }));
  await render(<ModelList />);
  assert.match(container.querySelector('[role="status"]')!.textContent!, /Memuat/);
  await act(async () => resolve(Response.json(page([])))); await settle();
  assert.match(container.textContent!, /Belum ada model/);
});

test("category creation and deactivation send typed status and version", async () => {
  const writes: Record<string, unknown>[] = [];
  mock((_url, init) => { writes.push(JSON.parse(String(init.body))); return Response.json(category, { status: 201 }); });
  await render(<MasterManager />);
  await change(input("Nama kategori"), "Printer"); await change(input("Kode kategori"), "PRINTER");
  await submit(container.querySelector('form[aria-label="Form kategori"]')!);
  assert.equal(writes[0].code, "printer"); assert.equal(writes[0].is_active, true); assert.equal(writes[0].version, undefined);
  await click(container.querySelector('button[aria-label="Edit Access Point"]')!);
  await click(input("Kategori aktif")); await submit(container.querySelector('form[aria-label="Form kategori"]')!);
  assert.equal(writes[1].is_active, false); assert.equal(writes[1].version, 1);
});

test("manufacturer creation clears empty website to null", async () => {
  let body: Record<string, unknown> | undefined;
  mock((_url, init) => { body = JSON.parse(String(init.body)); return Response.json(maker, { status: 201 }); });
  await render(<MasterManager />); await change(input("Nama produsen"), "Synthetic Maker");
  await submit(container.querySelector('form[aria-label="Form produsen"]')!);
  assert.equal(body?.name, "Synthetic Maker"); assert.equal(body?.website, null);
});

test("gallery has private image fallback and confirms versioned deletion", async () => {
  const photo = { id: "photo", device_model_id: model.id, content_url: `/api/v1/device-models/${model.id}/reference-images/photo/content`, is_primary: true, angle: "Depan", byte_size: 1024, mime_type: "image/png", sha256: "synthetic", created_at: "" };
  let deleted = false; let target = "";
  mock((url, init) => { if (init.method === "DELETE") { deleted = true; target = url; return new Response(null, { status: 204 }); } return Response.json({ items: deleted ? [] : [photo], model_version: deleted ? 8 : 7 }); });
  await render(<Gallery model={model} editable onChanged={() => undefined} onBusy={() => undefined} />);
  const img = container.querySelector("img")!; assert.equal(img.getAttribute("src"), photo.content_url);
  await act(async () => img.dispatchEvent(new win.Event("error")));
  assert.match(container.textContent!, /Foto belum dapat dimuat/); await click(button("Muat ulang foto"));
  assert.ok(container.querySelector("img"));
  await click(button("Hapus foto")); assert.equal(deleted, false); await click(button("Ya, lanjutkan"));
  assert.equal(target, `/api/v1/device-models/${model.id}/reference-images/photo?version=7`);
  assert.match(container.textContent!, /Foto telah dihapus/); assert.equal(container.querySelector("img"), null);
});

test("detail background refresh retains partial gallery upload errors", async () => {
  let writes = 0;
  mock((url, init) => {
    if (init.method === "POST") return ++writes === 1 ? Response.json({ image: { id: "one" }, model_version: 2 }, { status: 201 }) : Response.json({ detail: "bad image" }, { status: 415 });
    return Response.json(url.includes("reference-images") ? { items: [], model_version: writes ? 2 : 1 } : { ...model, version: writes ? 2 : 1 });
  });
  await render(<ModelDetail id={model.id} />);
  Object.defineProperty(input("Pilih foto"), "files", { configurable: true, value: [new File(["one"], "one.png", { type: "image/png" }), new File(["two"], "two.png", { type: "image/png" })] });
  await submit(container.querySelector('form[aria-label="Unggah foto referensi"]')!); await settle(); await settle();
  assert.match(container.textContent!, /1 foto sudah berhasil/); assert.match(container.querySelector('[role="alert"]')!.textContent!, /Format foto/);
});
