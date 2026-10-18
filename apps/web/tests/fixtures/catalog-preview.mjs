// Read-only synthetic API for visual UI review. Never connects to PostgreSQL or private storage.
import { createServer } from "node:http";
import { URL } from "node:url";
import { env } from "node:process";
import { log } from "node:console";
const id = index => `00000000-0000-0000-0000-${String(index).padStart(12, "0")}`;
const base = { is_active: true, version: 1, created_at: "2026-10-18T00:00:00Z", updated_at: "2026-10-18T00:00:00Z" };
const categories = ["Access Point", "Router", "Switch", "CCTV", "Printer"].map((name, i) => ({ ...base, id: id(i + 1), name, code: name.toLowerCase().replaceAll(" ", "-"), description: null }));
const manufacturers = ["Ruijie", "Ubiquiti", "MikroTik"].map((name, i) => ({ ...base, id: id(i + 10), name, website: null }));
const models = ["AP680-L", "AP650", "EdgeRouter X", "Switch 24 PoE"].map((model_name, i) => ({ ...base, id: id(i + 100), model_name, manufacturer_id: manufacturers[i % 3].id, category_id: categories[i > 1 ? i - 1 : 0].id, environment: i === 0 ? "outdoor" : "indoor", aliases: ["Model sintetis"], description: "Contoh sintetis untuk peninjauan UI. Tidak terhubung ke data development.", specs: { jumlah_port: 4, poe: true, koneksi: ["2.4 GHz", "5 GHz"] }, is_active: i !== 3 }));
const wrap = items => ({ items, total: items.length, page: 1, page_size: 15, total_pages: items.length ? 1 : 0 });
createServer((request, response) => {
  const url = new URL(request.url, "http://preview");
  response.setHeader("content-type", "application/json");
  response.setHeader("cache-control", "no-store");
  if (request.method !== "GET") { response.writeHead(405); response.end(JSON.stringify({ detail: "Read-only synthetic preview" })); return; }
  let body;
  if (url.pathname === "/api/v1/auth/me") body = { id: id(999), name: "Preview Sintetis", email: "preview@example.invalid", role: env.PREVIEW_ROLE ?? "ADMIN" };
  else if (url.pathname === "/api/v1/device-categories") body = wrap(categories);
  else if (url.pathname === "/api/v1/manufacturers") body = wrap(manufacturers);
  else if (url.pathname === "/api/v1/device-models") body = wrap(models.filter(model => (!url.searchParams.get("search") || model.model_name.toLowerCase().includes(url.searchParams.get("search").toLowerCase())) && (!url.searchParams.get("is_active") || String(model.is_active) === url.searchParams.get("is_active"))));
  else if (url.pathname.endsWith("/reference-images")) body = { items: [], model_version: 1 };
  else body = models.find(model => url.pathname === `/api/v1/device-models/${model.id}`);
  response.writeHead(body ? 200 : 404); response.end(JSON.stringify(body ?? { detail: "Not found" }));
}).listen(8000, "0.0.0.0", () => log("Synthetic read-only preview API ready"));
