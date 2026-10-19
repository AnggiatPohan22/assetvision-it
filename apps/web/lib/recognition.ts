import { catalogMutation, catalogRequest, CatalogError, type Page } from "./catalog";

export type Identifier = { kind: string; raw_value: string; normalized_value: string; source: string; issues: string[] };
export type Visual = { status: string; reason: string; encoder: { name: string; version: string } | null; candidates: { device_model_id: string; rank: number; similarity: number }[] };
export type OCR = { raw_text: string; corrected_text: string | null; reason: string; engine_version: string | null; ocr_candidates: Identifier[]; manual_candidates: Identifier[] };
export type Job = { id: string; kind: "MODEL" | "OCR"; content_url: string; result: Visual | OCR };
export type Unit = { asset_id: string; asset_version: number; device_model_id: string; manufacturer_id: string; archived: boolean; claims: {kind:string;value:string;verification:string;source:string}[] };
export type Survey = { id: string; version: 1; device_job_id: string; label_job_id: string | null; created_by: string; created_at: string; observed_at: string; notes: string; review_status: string; asset_id: string | null; evidence: {
 visual: Visual; ocr: OCR | null; location_name: string | null; force_unknown: boolean;
 fusion: { status: string; reasons: string[]; candidates: { asset_id: string; reasons: string[] }[] };
 unit_snapshots: Unit[]; asset_codes: Record<string,string>; model_names: Record<string,string>;
}; review: { reviewer_id: string; reviewed_at: string; decision: string; selected_asset_id: string | null; notes: string; evidence: { result_status: string } } | null };
export type Summary = { id: string; notes: string; created_at: string; review_status: string; result_status: string; location_name: string | null };
export const statusLabel: Record<string,string> = { UNKNOWN: "Tidak dikenali", UNKNOWN_MODEL: "Model belum dikenali", UNCERTAIN: "Model belum dapat dipastikan", KNOWN_MODEL_CANDIDATE: "Kandidat model", PROBABLE_ASSET: "Kandidat unit — perlu review", AMBIGUOUS: "Ambigu — beberapa unit mungkin cocok", CONFLICT: "Konflik bukti — perlu pemeriksaan", VERIFIED_ASSET: "Unit diverifikasi melalui review", PENDING: "Menunggu review", MATCH: "Cocok", MORE_PHOTOS: "Perlu foto tambahan", NEEDS_MORE_EVIDENCE: "Perlu bukti tambahan" };
export async function uploadRecognition(file: File, label = false) {
 const body = new FormData(); body.append("file",file);
 return recognitionMutation<Job>(`/recognition/${label ? "ocr" : "model-candidates"}`,body);
}
export const getSurveys = (page: number) => catalogRequest<Page<Summary>>(`/recognition/observations?page=${page}&page_size=10`);

export function evidenceReason(code:string) {
 const labels:Record<string,string> = {
  IDENTIFIER_MATCH:"Identifier cocok dengan klaim unit",MODEL_CANDIDATE_ONLY:"Kecocokan model hanya bukti pendukung",
  OFFICIAL_LOCATION_SUPPORT_ONLY:"Lokasi resmi sama, bukan bukti identitas tunggal",
  OFFICIAL_LOCATION_CONFLICT:"Lokasi pengamatan berbeda dari lokasi resmi",
  MODEL_IDENTIFIER_CONFLICT:"Model visual bertentangan dengan identifier unit",
  ARCHIVED_UNIT_REQUIRES_REVIEW:"Unit sudah diarsipkan",OBSERVATION_PRECEDES_OFFICIAL_LOCATION:"Pengamatan mendahului verifikasi lokasi resmi",
  LABEL_REVIEW_REQUIRED:"Label atau koreksi belum diperiksa manusia",SERIAL_MANUFACTURER_REQUIRED:"Serial memerlukan konteks produsen",
  IDENTIFIER_COLLISION:"Identifier yang sama diklaim beberapa unit",IDENTIFIERS_DISAGREE:"Identifier mengarah ke unit berbeda",
  MASTER_CLAIM_REVIEW_REQUIRED:"Klaim master belum terverifikasi",DISPUTED_MASTER_CLAIM:"Klaim master sedang diperselisihkan",
  CHECKED_IDENTIFIER_UNMATCHED:"Identifier yang diperiksa belum ditemukan",NON_DEVICE_MAC_ADDRESS:"MAC bukan alamat unit yang layak",
  IDENTIFIER_TYPE_NOT_UNIT_IDENTITY:"Tipe bukti belum membuktikan unit",NO_UNIT_EVIDENCE:"Belum ada bukti unit yang cukup",
  HUMAN_REVIEW_REQUIRED_NO_AUTO_VERIFICATION:"Keputusan manusia diperlukan; tidak ada verifikasi otomatis",
  LATEST_OBSERVATION_STALE_OR_LATER:"Observasi lain berada di luar waktu pembandingan",
  LATEST_OBSERVATION_MASTER_MISMATCH:"Observasi terakhir berbeda dari master",
  LATEST_OBSERVATION_SUPPORT_ONLY:"Observasi terakhir menjadi bukti pendukung",
  APPROVED_HISTORY_STALE_OR_LATER:"Riwayat perpindahan berada di luar waktu pembandingan",
  APPROVED_HISTORY_MASTER_MISMATCH:"Riwayat perpindahan berbeda dari master",
  APPROVED_HISTORY_SUPPORT_ONLY:"Riwayat perpindahan mendukung lokasi resmi",
  INVALID_IDENTIFIER:"Identifier tidak valid",INCONSISTENT_IDENTIFIER:"Nilai identifier tidak konsisten",
 };
 return labels[code]??"Bukti tambahan perlu diperiksa";
}

export async function recognitionMutation<T>(path:string, body:object|FormData):Promise<T> {
 try {
  const result = await catalogMutation<unknown>(path,"POST",body);
  const record = result as Partial<Survey> & Partial<Job> | null;
  const validId = typeof record?.id === "string" && /^[0-9a-f-]{36}$/i.test(record.id);
  const isSurvey = path.includes("/observations");
  if(!validId || (isSurvey ? !record?.evidence?.fusion || !Array.isArray(record.evidence.unit_snapshots) : !record?.result || typeof record.content_url!=="string"))
    throw new CatalogError(503,"Respons tidak lengkap; hasil belum pasti. Draft tetap ada. Periksa riwayat sebelum melanjutkan.");
  return result as T;
 }
 catch(error) {
  if(error instanceof CatalogError && error.status===409) throw new CatalogError(409,"Bukti, versi, atau status berubah. Draft tetap ada. Periksa riwayat dan muat ulang sebelum melanjutkan.",true);
  if(error instanceof CatalogError && error.status===429) throw new CatalogError(429,"Batas pemrosesan tercapai. Tunggu satu menit, lalu periksa riwayat sebelum melanjutkan.");
  throw error;
 }
}

export const identifierName = (kind:string) => ({SERIAL_NUMBER:"Serial number",MAC_LAN:"MAC LAN",MAC_WLAN:"MAC WLAN",BSSID:"BSSID",MAC:"MAC belum bertipe",MODEL:"Teks model"}[kind]??kind);
