import { CatalogError, catalogRequest, type DeviceModel, type Manufacturer, type Page } from "./catalog";

export const statuses = { IN_STOCK: "Dalam stok", IN_USE: "Digunakan", MAINTENANCE: "Pemeliharaan", RETIRED: "Pensiun", ARCHIVED: "Diarsipkan" };
export const conditions = { UNKNOWN: "Belum diketahui", GOOD: "Baik", DAMAGED: "Rusak", UNUSABLE: "Tidak dapat digunakan" };
export const identifierTypes = { SERIAL_NUMBER: "Serial number", MAC_LAN: "MAC LAN", MAC_WLAN: "MAC WLAN", BSSID: "BSSID", HOSTNAME: "Hostname", MANAGEMENT_ID: "Management ID" };
export const sources = { MANUAL: "Manual", IMPORT: "Impor", CONTROLLER: "Controller" };
export const verifications = { UNVERIFIED: "Belum diverifikasi", VERIFIED: "Terverifikasi", DISPUTED: "Diperdebatkan" };
export type Asset = { id: string; asset_code: string; device_model_id: string; lifecycle_status: keyof typeof statuses; condition: keyof typeof conditions; notes: string | null; purchase_date: string | null; installed_at: string | null; created_at: string; updated_at: string; version: number };
export type Identifier = { id: string; asset_id: string; identifier_type: keyof typeof identifierTypes; raw_value: string; normalized_value: string; source: keyof typeof sources; verification_status: keyof typeof verifications; notes: string | null; version: number; collision_asset_ids: string[] };
export type IdentifierResult = { identifier: Identifier; asset_version: number };
export type AssetEvent = { id: string; asset_id: string; actor_id: string; event_type: string; recorded_at: string; before_json: Record<string, unknown> | null; after_json: Record<string, unknown> };
export type CsvRow = { row: number; asset_code: string; valid: boolean; errors: string[]; collisions: { identifier_type: string; normalized_value: string; asset_ids: string[]; csv_rows: number[] }[]; location_hint: string | null; asset_id: string | null; version: number | null };
export type Preview = { total_rows: number; valid_rows: number; invalid_rows: number; has_collisions: boolean; rows: CsvRow[] };
export type ImportResult = { import_id: string; status: "COMMITTED" | "REJECTED"; created_count: number; failed_count: number; rows: CsvRow[]; errors: string[] };
export type ImportPayload = { csv_text: string; idempotency_key: string; allow_identifier_collisions: boolean };
export const errorFrom = (cause: unknown) => cause instanceof Error ? cause : new Error("Permintaan belum dapat diselesaikan.");

export function assetQuery(filters: { search: string; model: string; status: string; page: number }, exporting = false) {
  const query = new URLSearchParams(exporting ? {} : { page: String(filters.page), page_size: "15" });
  if (filters.search.trim()) query.set("search", filters.search.trim());
  if (filters.model) query.set("model_id", filters.model);
  if (filters.status) query.set("status", filters.status);
  return `/assets${exporting ? "/export.csv" : ""}?${query}`;
}

export async function assetModels(signal?: AbortSignal): Promise<{ models: DeviceModel[]; makers: Manufacturer[] }> {
  async function all<T>(path: string) {
    const items: T[] = [];
    for (let page = 1; ; page++) {
      const result = await catalogRequest<Page<T>>(`${path}?page_size=100&page=${page}`, { signal });
      items.push(...result.items);
      if (page >= result.total_pages) return items;
    }
  }
  const [models, makers] = await Promise.all([all<DeviceModel>("/device-models"), all<Manufacturer>("/manufacturers")]);
  return { models, makers };
}

export async function assetMutation<T>(path: string, method: "POST" | "PATCH" | "DELETE", body?: object): Promise<T> {
  const { csrf_token } = await catalogRequest<{ csrf_token: string }>("/auth/session");
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { method, credentials: "same-origin", cache: "no-store", headers: { "X-CSRF-Token": csrf_token, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  } catch { throw new CatalogError(503, "Koneksi terputus; hasil belum diketahui. Periksa data terbaru sebelum menyimpan lagi. Untuk impor, gunakan tombol coba ulang dengan permintaan yang sama."); }
  const result = await response.json().catch(() => null);
  if (response.ok && (result === null || typeof result !== "object" || Array.isArray(result))) {
    throw new CatalogError(503, "Respons penyimpanan tidak lengkap; hasil belum diketahui. Periksa data terbaru. Untuk impor, coba ulang permintaan yang sama.");
  }
  if (response.ok || (response.status === 409 && result?.status === "REJECTED" && path === "/assets/imports/commit")) return result as T;
  if (response.status === 401) throw new CatalogError(401, "Sesi berakhir. Masuk kembali untuk melanjutkan.");
  if (response.status === 403) throw new CatalogError(403, "Akses ditolak atau sesi keamanan berubah. Muat ulang atau masuk kembali.");
  if (response.status === 409) {
    const version = /changed|reload|version/i.test(String(result?.detail));
    throw new CatalogError(409, version ? "Data telah berubah. Isian tetap ada; muat ulang sebelum menyimpan kembali." : "Kode atau identifier sudah digunakan, model tidak aktif, atau kunci impor tidak cocok. Periksa data sebelum mencoba lagi.", version);
  }
  if (response.status === 422 || response.status === 400) {
    const detail = typeof result?.detail === "string" ? ` ${result.detail}` : "";
    throw new CatalogError(response.status, `Isian tidak valid. Periksa format kode, identifier, model, tanggal, atau CSV beserta header wajibnya.${detail}`);
  }
  if (response.status === 413) throw new CatalogError(413, "Ukuran isian melebihi batas. CSV maksimal 256 KiB dan 500 baris.");
  throw new CatalogError(response.status, "Permintaan gagal. Periksa data terbaru sebelum mengirim perubahan lagi.");
}

export type AssetDraft = { asset_code: string; device_model_id: string; lifecycle_status: Asset["lifecycle_status"]; condition: Asset["condition"]; notes: string; purchase_date: string; installed_at: string };
export const assetDraft = (asset?: Asset): AssetDraft => ({ asset_code: asset?.asset_code ?? "", device_model_id: asset?.device_model_id ?? "", lifecycle_status: asset?.lifecycle_status ?? "IN_STOCK", condition: asset?.condition ?? "UNKNOWN", notes: asset?.notes ?? "", purchase_date: asset?.purchase_date ?? "", installed_at: asset?.installed_at ?? "" });
export function assetPayload(draft: AssetDraft, initial?: Asset) {
  const code = draft.asset_code.trim().toUpperCase();
  if (!initial && !/^[A-Z0-9][A-Z0-9_-]{0,49}$/.test(code)) throw new Error("Asset ID wajib 1–50 huruf/angka, garis bawah atau tanda hubung, diawali huruf/angka.");
  if (!draft.device_model_id) throw new Error("Pilih model perangkat dari katalog.");
  if (draft.notes.length > 4000) throw new Error("Catatan maksimal 4000 karakter.");
  if (draft.purchase_date && !/^\d{4}-\d{2}-\d{2}$/.test(draft.purchase_date)) throw new Error("Tanggal pembelian harus YYYY-MM-DD.");
  if (draft.installed_at && (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(draft.installed_at) || !Number.isFinite(Date.parse(draft.installed_at)))) throw new Error("Waktu pemasangan harus ISO 8601 dengan zona waktu, misalnya 2026-10-19T08:00:00+08:00.");
  const payload = { device_model_id: draft.device_model_id, lifecycle_status: draft.lifecycle_status, condition: draft.condition, notes: draft.notes || null, purchase_date: draft.purchase_date || null, installed_at: draft.installed_at || null, ...(initial ? { version: initial.version } : { asset_code: code }) };
  boundedJson(payload);
  return payload;
}
export function boundedJson(payload: object) {
  if (new TextEncoder().encode(JSON.stringify(payload)).length > 16384) throw new Error("Isian terlalu panjang; kurangi catatan.");
}
export function validateIdentifier(type: Identifier["identifier_type"], raw: string) {
  const value = raw.trim();
  if (!value || raw.length > 255 || Array.from(raw).some(char => { const code = char.codePointAt(0)!; return code < 32 || (code >= 0xd800 && code <= 0xdfff); })) throw new Error("Nilai identifier wajib diisi, maksimal 255 karakter yang dapat dibaca.");
  if (type === "SERIAL_NUMBER" && ["UNKNOWN", "N/A", "NA", "-"].includes(value.toUpperCase())) throw new Error("SN tidak tersedia: jangan membuat identifier atau SN palsu.");
  if (["MAC_LAN", "MAC_WLAN", "BSSID"].includes(type) && !/^(?:[0-9a-f]{12}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|(?:[0-9a-f]{2}-){5}[0-9a-f]{2}|(?:[0-9a-f]{4}\.){2}[0-9a-f]{4})$/i.test(value)) throw new Error("Format MAC tidak valid, misalnya AA:BB:CC:DD:EE:FF.");
}
export async function readCsv(file: Pick<File, "size" | "arrayBuffer">) {
  if (!file.size || file.size > 256 * 1024) throw new Error("Pilih CSV tidak kosong, maksimal 256 KiB.");
  let text: string;
  try { text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()); }
  catch { throw new Error("CSV harus menggunakan encoding UTF-8 yang valid."); }
  if (!text.trim()) throw new Error("CSV kosong.");
  return text;
}
