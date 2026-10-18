import type { DeviceModel, Scalar, Specs } from "./catalog";

export type ScalarDraft = { kind: "text" | "number" | "boolean" | "empty"; value: string };
export type SpecDraft = { key: string; kind: ScalarDraft["kind"] | "list"; value: string; items: ScalarDraft[] };
export type ModelDraft = { model_name: string; manufacturer_id: string; category_id: string; aliases: string; description: string; environment: DeviceModel["environment"]; is_active: boolean; specs: SpecDraft[] };
export function scalarDraft(value: Scalar): ScalarDraft {
  return { kind: value === null ? "empty" : typeof value === "number" ? "number" : typeof value === "boolean" ? "boolean" : "text", value: value === null ? "" : String(value) };
}
export function newDraft(model?: DeviceModel): ModelDraft {
  return { model_name: model?.model_name ?? "", manufacturer_id: model?.manufacturer_id ?? "", category_id: model?.category_id ?? "",
    aliases: model?.aliases.join("\n") ?? "", description: model?.description ?? "", environment: model?.environment ?? "both", is_active: model?.is_active ?? true,
    specs: Object.entries(model?.specs ?? {}).map(([key, value]) => Array.isArray(value)
      ? { key, kind: "list", value: "", items: value.map(scalarDraft) }
      : { key, ...scalarDraft(value), items: [] }),
  };
}
const normalize = (value: string) => value.trim().replace(/\s+/g, " ");
function scalarValue(draft: ScalarDraft): Scalar {
  if (draft.kind === "empty") return null;
  if (draft.kind === "boolean") return draft.value === "true";
  if (draft.kind === "number") {
    const value = Number(draft.value);
    if (!draft.value.trim() || !Number.isFinite(value) || Math.abs(value) > 1e12) throw new Error("Isi angka spesifikasi yang valid, antara -1 triliun dan 1 triliun.");
    return value;
  }
  if (draft.value.length > 500) throw new Error("Nilai teks spesifikasi maksimal 500 karakter.");
  return draft.value;
}
export function modelPayload(draft: ModelDraft, initial?: DeviceModel) {
  const model_name = normalize(draft.model_name);
  if (!model_name || model_name.length > 200) throw new Error("Nama model wajib diisi, maksimal 200 karakter.");
  if (!draft.category_id || !draft.manufacturer_id) throw new Error("Pilih kategori dan produsen.");
  const aliases = draft.aliases.split("\n").map(normalize).filter(Boolean);
  if (aliases.length > 20 || aliases.some(value => value.length > 200)) throw new Error("Maksimal 20 nama alternatif, masing-masing 200 karakter.");
  if (new Set(aliases.map(value => value.toLowerCase())).size !== aliases.length) throw new Error("Nama alternatif tidak boleh berulang.");
  if (draft.description.length > 4000) throw new Error("Deskripsi maksimal 4000 karakter.");
  const specs: Specs = Object.create(null);
  if (draft.specs.length > 32) throw new Error("Maksimal 32 spesifikasi.");
  for (const row of draft.specs) {
    const key = row.key.trim();
    if (!/^[A-Za-z0-9_.-]{1,64}$/.test(key)) throw new Error("Nama spesifikasi wajib diisi; gunakan huruf, angka, titik, garis bawah, atau tanda hubung (maksimal 64).");
    if (Object.hasOwn(specs, key)) throw new Error("Nama spesifikasi harus unik.");
    if (row.items.length > 20) throw new Error("Daftar spesifikasi maksimal 20 nilai.");
    specs[key] = row.kind === "list" ? row.items.map(scalarValue) : scalarValue(row as ScalarDraft);
  }
  const jsonScalar = (value: Scalar) => JSON.stringify(value);
  const encoded = "{" + Object.entries(specs).map(([key, value]) => `${JSON.stringify(key)}: ${Array.isArray(value) ? "[" + value.map(jsonScalar).join(", ") + "]" : jsonScalar(value)}`).join(", ") + "}";
  if (new TextEncoder().encode(encoded).length > 8192) throw new Error("Spesifikasi terlalu panjang. Kurangi jumlah atau panjang nilainya.");
  const payload = { model_name, manufacturer_id: draft.manufacturer_id, category_id: draft.category_id, aliases,
    description: draft.description || null, environment: draft.environment, is_active: draft.is_active, specs,
    ...(initial ? { version: initial.version } : {}),
  };
  if (new TextEncoder().encode(JSON.stringify(payload)).length > 16384) throw new Error("Isian model terlalu panjang. Kurangi deskripsi atau nama alternatif.");
  return payload;
}
