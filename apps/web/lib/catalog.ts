export type Role = "ADMIN" | "OFFICER" | "VIEWER";
export type CatalogRecord = { id: string; is_active: boolean; version: number; created_at: string; updated_at: string };
export type Category = CatalogRecord & { code: string; name: string; description: string | null };
export type Manufacturer = CatalogRecord & { name: string; website: string | null };
export type Scalar = string | number | boolean | null;
export type Specs = Record<string, Scalar | Scalar[]>;
export type DeviceModel = CatalogRecord & {
  category_id: string; manufacturer_id: string; model_name: string; aliases: string[];
  description: string | null; environment: "indoor" | "outdoor" | "both"; specs: Specs;
};
export type Page<T> = { items: T[]; page: number; page_size: number; total: number; total_pages: number };
export type ReferenceImage = {
  id: string; device_model_id: string; sha256: string; mime_type: string; byte_size: number;
  angle: string | null; is_primary: boolean; content_url: string; created_at: string;
};
export type ImageList = { items: ReferenceImage[]; model_version: number };
export type ImageUpload = { image: ReferenceImage; model_version: number };
export const environmentNames = { indoor: "Dalam ruangan", outdoor: "Luar ruangan", both: "Keduanya" };
export const canManage = (role: Role) => role === "ADMIN";

export class CatalogError extends Error {
  constructor(public status: number, message: string, public conflict = false) { super(message); }
}

function responseError(status: number, body: unknown): CatalogError {
  const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : "";
  const text = typeof detail === "string" ? detail : "";
  if (status === 401) return new CatalogError(status, "Sesi Anda berakhir. Masuk kembali untuk melanjutkan.");
  if (status === 403) return new CatalogError(status, "Akses ditolak atau sesi keamanan berubah. Muat ulang atau masuk kembali.");
  if (status === 404) return new CatalogError(status, "Data yang diminta tidak ditemukan.");
  if (status === 409) {
    if (/changed|reload|version/i.test(text)) return new CatalogError(status, "Data telah berubah. Isian Anda tetap ada. Muat ulang data sebelum mengirim kembali.", true);
    if (/count limit/i.test(text)) return new CatalogError(status, "Jumlah foto sudah mencapai batas workspace.");
    if (/archived/i.test(text)) return new CatalogError(status, "Model yang diarsipkan tidak dapat menerima foto baru.");
    if (/inactive/i.test(text)) return new CatalogError(status, "Pilih kategori dan produsen yang aktif sebelum melanjutkan.");
    return new CatalogError(status, "Nama atau kode sudah digunakan, atau referensi tidak lagi valid. Periksa isian Anda.");
  }
  if (status === 413) return new CatalogError(status, "Ukuran unggahan atau isian terlalu besar. Kurangi ukurannya lalu coba lagi.");
  if (status === 415) return new CatalogError(status, "Format foto tidak sesuai. Gunakan JPEG, PNG, atau WebP yang valid.");
  if (status === 422 || status === 400) return new CatalogError(status, "Isian atau foto tidak valid. Periksa nama, spesifikasi, ukuran, dimensi, dan jenis foto.");
  return new CatalogError(status, "Layanan belum dapat dihubungi. Coba lagi tanpa mengirim ulang perubahan secara otomatis.");
}

export async function catalogRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, credentials: "same-origin", cache: "no-store" });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new CatalogError(503, "Koneksi terputus. Periksa data terbaru sebelum mencoba menyimpan lagi.");
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw responseError(response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function catalogMutation<T>(path: string, method: "POST" | "PATCH" | "DELETE", body?: object | FormData, signal?: AbortSignal): Promise<T> {
  const { csrf_token } = await catalogRequest<{ csrf_token: string }>("/auth/session", { signal });
  const multipart = body instanceof FormData;
  return catalogRequest<T>(path, { method, signal,
    headers: { "X-CSRF-Token": csrf_token, ...(!multipart && body ? { "Content-Type": "application/json" } : {}) },
    body: body ? multipart ? body : JSON.stringify(body) : undefined,
  });
}

export async function catalogOptions<T>(resource: "device-categories" | "manufacturers", signal?: AbortSignal): Promise<T[]> {
  const items: T[] = [];
  let page = 1;
  while (true) {
    const result = await catalogRequest<Page<T>>(`/${resource}?page_size=100&page=${page}`, { signal });
    items.push(...result.items);
    if (page >= result.total_pages) return items;
    page++;
  }
}

export function validatePhoto(file: Pick<File, "size" | "type">): void {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error("Gunakan foto JPEG, PNG, atau WebP.");
  if (!file.size || file.size > 8 * 1024 * 1024) throw new Error("Pilih foto tidak kosong, maksimal 8 MiB per file.");
}

export function modelQuery(filters: { search: string; category: string; manufacturer: string; status: string; page: number }): string {
  const query = new URLSearchParams({ page: String(filters.page), page_size: "15" });
  if (filters.search.trim()) query.set("search", filters.search.trim());
  if (filters.category) query.set("category_id", filters.category);
  if (filters.manufacturer) query.set("manufacturer_id", filters.manufacturer);
  if (filters.status !== "all") query.set("is_active", filters.status);
  return `/device-models?${query}`;
}
