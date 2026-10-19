import { CatalogError, catalogRequest, type Role } from "./catalog";
import { boundedJson } from "./assets";

export const kinds = { SITE: "Site", AREA: "Area", BUILDING: "Bangunan", FLOOR: "Lantai", ROOM: "Ruangan", SPOT: "Titik" };
export type Location = { id: string; parent_id: string | null; code: string; name: string; kind: keyof typeof kinds; is_active: boolean; version: number; latitude: number | null; longitude: number | null; gps_accuracy_m: number | null; gps_recorded_at: string | null };
export type Tree = { items: Location[]; total: number };
export type Movement = { id: string; asset_id: string; from_location_id: string | null; to_location_id: string; status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED"; reason: string; requested_by: string; requested_at: string; expected_asset_version: number; request_snapshot_json: { from: Location | null; to: Location }; reviewed_by: string | null; reviewed_at: string | null; review_reason: string | null; effective_at: string | null; version: number };
export type Observation = { id: string; asset_id: string | null; observed_location_id: string; observed_by: string; observed_at: string; recorded_at: string; evidence_note: string; comparison_status: string; review_status: "PENDING" | "ACKNOWLEDGED" | "DISMISSED"; reviewed_by: string | null; reviewed_at: string | null; review_reason: string | null; snapshot_json: { observed_location: Location; official_location: Location | null }; version: number };
export type LocationStatus = { asset_id: string; asset_version: number; current_location_id: string | null; location_verified_at: string | null; status: string; location_conflict: boolean; latest_observation: Observation | null };
export type TimelineEvent = { id: string; source: string; actor_id: string; event_type: string; occurred_at: string; recorded_at: string; payload_json: Record<string, unknown> };
export const movementNames = { PENDING: "Menunggu review", APPROVED: "Disetujui", REJECTED: "Ditolak", CANCELLED: "Dibatalkan" };
export const reviewNames = { PENDING: "Menunggu review", ACKNOWLEDGED: "Sudah ditinjau", DISMISSED: "Dikesampingkan" };
export const statusNames: Record<string,string> = { UNPLACED: "Belum ditempatkan", NO_OBSERVATION: "Belum ada observasi aktif", STALE_OBSERVATION: "Observasi mendahului verifikasi resmi", MATCH: "Observasi sesuai lokasi resmi", LOCATION_CONFLICT: "LOCATION_CONFLICT — Lokasi berbeda" };
export const eventNames: Record<string,string> = { CREATE: "Aset dibuat", UPDATE: "Metadata diperbarui", ARCHIVE: "Aset diarsipkan", INITIAL_PLACEMENT: "Penempatan awal", MOVEMENT_REQUESTED: "Perpindahan diajukan", MOVEMENT_APPROVED: "Perpindahan disetujui", MOVEMENT_REJECTED: "Perpindahan ditolak", MOVEMENT_CANCELLED: "Perpindahan dibatalkan", LOCATION_OBSERVED: "Lokasi diamati", LOCATION_OBSERVATION_REVIEWED: "Observasi ditinjau" };
export const canObserve = (role: Role) => role === "ADMIN" || role === "OFFICER";
export function reasonValue(value: string) {
  const text = value.trim().replace(/\s+/g," ");
  if (!text || text.length > 2000 || Array.from(text).some(char=>char.codePointAt(0)!<32||char.codePointAt(0)===127)) throw new Error("Alasan/catatan wajib diisi, maksimal 2000 karakter yang dapat dibaca.");
  return text;
}
export function locationName(id: string | null, locations: Location[]) {
  if (!id) return "Belum ditempatkan";
  const item = locations.find(item => item.id === id);
  return item ? `${item.name} (${item.code})${item.is_active ? "" : " · diarsipkan"}` : id;
}
export function locationPath(item: Location, items: Location[], index?: Map<string,Location>) {
  const byId = index ?? new Map(items.map(item => [item.id,item]));
  const names: string[] = []; const seen = new Set<string>();
  let current: Location | undefined = item;
  while (current && !seen.has(current.id)) { seen.add(current.id); names.unshift(current.name); current = current.parent_id ? byId.get(current.parent_id) : undefined; }
  return names.join(" → ");
}
export function descendants(id: string, items: Location[]) {
  const result = new Set([id]); const children = new Map<string, string[]>();
  for (const item of items) if (item.parent_id) children.set(item.parent_id,[...(children.get(item.parent_id) ?? []),item.id]);
  const queue=[id]; while(queue.length) for(const child of children.get(queue.pop()!) ?? []) if(!result.has(child)) { result.add(child); queue.push(child); }
  return result;
}
export function treeRows(items: Location[]) {
  const rows: { item: Location; depth: number }[]=[]; const seen=new Set<string>();
  const children=new Map<string|null,Location[]>();
  for(const item of items) children.set(item.parent_id,[...(children.get(item.parent_id)??[]),item]);
  const ids=new Set(items.map(item=>item.id));
  const stack=items.filter(item=>!item.parent_id||!ids.has(item.parent_id)).reverse().map(item=>({item,depth:0}));
  while(stack.length) { const row=stack.pop()!; if(seen.has(row.item.id)) continue; seen.add(row.item.id); rows.push(row); for(const child of [...(children.get(row.item.id)??[])].reverse()) stack.push({item:child,depth:row.depth+1}); }
  return rows;
}
// Domain-specific errors and unknown-result blocking are shared by every location write.
export async function locationMutation<T>(path: string, method: "POST" | "PATCH", body: object): Promise<T> {
  boundedJson(body);
  const { csrf_token }=await catalogRequest<{csrf_token:string}>("/auth/session");
  let response: Response;
  try { response=await fetch(`/api/v1${path}`,{method,credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf_token},body:JSON.stringify(body)}); }
  catch { throw new CatalogError(503,"Koneksi terputus; hasil belum diketahui. Muat ulang dan periksa riwayat sebelum mengirim lagi."); }
  const data=await response.json().catch(()=>null);
  if(response.ok && data && typeof data==="object" && !Array.isArray(data)) return data as T;
  if(response.status===401) throw new CatalogError(401,"Sesi berakhir. Masuk kembali untuk melanjutkan.");
  if(response.status===403) throw new CatalogError(403,"Akses ditolak atau sesi keamanan berubah. Muat ulang atau masuk kembali.");
  if(response.status===409) throw new CatalogError(409,"Data/versi atau status telah berubah; bisa juga terjadi kode duplikat atau siklus hierarki. Isian tetap ada. Batalkan dan muat ulang sebelum mencoba lagi.",true);
  if(response.status===422||response.status===400) throw new CatalogError(response.status,"Isian tidak valid. Periksa lokasi, alasan, waktu dan koordinat.");
  throw new CatalogError(response.status,"Penyimpanan belum dapat dipastikan. Muat ulang dan periksa riwayat sebelum mencoba lagi.");
}
