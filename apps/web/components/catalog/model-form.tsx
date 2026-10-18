"use client";
import { useState, type FormEvent } from "react";
import { canManage, catalogMutation, environmentNames, type DeviceModel } from "../../lib/catalog";
import { modelPayload, newDraft } from "../../lib/catalog-form";
import { useCatalogOptions } from "./options";
import { ErrorNotice, Loading, useCatalogRole } from "./shared";
import SpecEditor from "./spec-editor";

export default function ModelForm({ initial, onSaved, onCancel, onReload }: { initial?: DeviceModel; onSaved: (model: DeviceModel) => void; onCancel?: () => void; onReload?: () => void }) {
  const role = useCatalogRole();
  const options = useCatalogOptions();
  // The edit version belongs to this draft, even if a background read returns newer data.
  const [baseline] = useState(initial);
  const [draft, setDraft] = useState(() => newDraft(initial));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  if (!canManage(role)) return <p>Hanya administrator yang dapat mengelola model.</p>;
  if (options.error) return <ErrorNotice error={options.error} retry={options.reload} />;
  if (!options.categories || !options.manufacturers) return <Loading />;
  const field = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft(old => ({ ...old, [key]: value }));
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(undefined);
    try {
      const payload = modelPayload(draft, baseline);
      setBusy(true);
      const saved = await catalogMutation<DeviceModel>(baseline ? `/device-models/${baseline.id}` : "/device-models", baseline ? "PATCH" : "POST", payload);
      onSaved(saved);
    } catch (cause) { setError(cause instanceof Error ? cause : new Error("Model belum dapat disimpan.")); }
    finally { setBusy(false); }
  }
  const missing = !options.categories.some(value => value.is_active) || !options.manufacturers.some(value => value.is_active);
  return <form onSubmit={submit} className="catalog-panel catalog-model-form" aria-label={initial ? "Edit model" : "Tambah model"}>
    {missing && <p className="catalog-notice">Kategori dan produsen aktif diperlukan untuk model baru atau pemulihan. <a className="catalog-link" href="/catalog/settings">Kelola kategori & produsen</a>.</p>}
    <fieldset disabled={busy}><legend className="sr-only">Data model perangkat</legend><div className="catalog-form-grid">
      <label>Nama model *<input required maxLength={200} value={draft.model_name} onChange={event => field("model_name", event.target.value)} /></label>
      <label>Produsen *<select required value={draft.manufacturer_id} onChange={event => field("manufacturer_id", event.target.value)}><option value="">Pilih produsen</option>{options.manufacturers.map(value => <option key={value.id} value={value.id} disabled={!value.is_active && value.id !== baseline?.manufacturer_id}>{value.name}{!value.is_active ? " (diarsipkan)" : ""}</option>)}</select></label>
      <label>Kategori *<select required value={draft.category_id} onChange={event => field("category_id", event.target.value)}><option value="">Pilih kategori</option>{options.categories.map(value => <option key={value.id} value={value.id} disabled={!value.is_active && value.id !== baseline?.category_id}>{value.name}{!value.is_active ? " (diarsipkan)" : ""}</option>)}</select></label>
      <label>Lingkungan<select value={draft.environment} onChange={event => field("environment", event.target.value as DeviceModel["environment"])}>{Object.entries(environmentNames).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
      <label className="catalog-wide">Deskripsi<textarea rows={3} maxLength={4000} value={draft.description} onChange={event => field("description", event.target.value)} /></label>
      <label className="catalog-wide">Nama alternatif<textarea rows={3} value={draft.aliases} onChange={event => field("aliases", event.target.value)} /><span className="catalog-hint">Satu nama per baris. Maksimal 20 nama, tanpa pengulangan.</span></label>
      <label className="catalog-check catalog-wide"><input type="checkbox" checked={draft.is_active} onChange={event => field("is_active", event.target.checked)} />Model aktif</label>
    </div><SpecEditor rows={draft.specs} onChange={value => field("specs", value)} />
    <div className="catalog-actions"><button type="submit">{busy ? "Menyimpan…" : "Simpan model"}</button>{onCancel && <button className="secondary" type="button" onClick={onCancel}>Batalkan edit</button>}</div></fieldset>
    {error && <><ErrorNotice error={error} />{initial && onReload && <button type="button" className="secondary" onClick={onReload}>Muat ulang formulir dan buang isian</button>}</>}
    <p className="catalog-hint">* Wajib diisi. Katalog mendeskripsikan model perangkat, bukan unit fisik.</p>
  </form>;
}
