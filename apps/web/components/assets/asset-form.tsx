"use client";
import { useRef, useState, type FormEvent } from "react";
import { CatalogError } from "../../lib/catalog";
import { assetDraft, assetPayload, assetMutation, conditions, statuses, errorFrom, type Asset } from "../../lib/assets";
import { ErrorNotice } from "../catalog/shared";
import { useAssetModels, modelLabel } from "./model-options";
export default function AssetForm({ initial, onSaved, onCancel, onReload }: { initial?: Asset; onSaved: (asset: Asset) => void; onCancel?: () => void; onReload?: () => void }) {
  // Freeze version and draft for this editing session.
  const [base] = useState(initial);
  const [draft, setDraft] = useState(() => assetDraft(initial));
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<Error>();
  const [blocked, setBlocked] = useState(false);
  const options = useAssetModels();
  const update = (key: keyof typeof draft, value: string) => setDraft(old => ({ ...old, [key]: value }));
  async function save(event: FormEvent) {
    event.preventDefault(); if (lock.current || blocked) return;
    lock.current = true; setBusy(true); setError(undefined);
    try { const payload = assetPayload(draft, base); onSaved(await assetMutation<Asset>(`/assets${base ? `/${base.id}` : ""}`, base ? "PATCH" : "POST", payload)); }
    catch (cause) { const failure = errorFrom(cause); setError(failure); if (failure instanceof CatalogError && (failure.status === 409 || failure.status >= 500)) setBlocked(true); }
    finally { lock.current = false; setBusy(false); }
  }
  return <form className="catalog-panel" aria-label={base ? "Edit aset" : "Tambah aset"} onSubmit={save}><fieldset disabled={busy}><legend>{base ? "Edit metadata unit" : "Unit fisik baru"}</legend><div className="catalog-form-grid">
    <label>Asset ID<input value={draft.asset_code} disabled={!!base} required maxLength={50} onChange={event => update("asset_code", event.target.value)} /><span className="catalog-hint">Permanen, unik, tidak dapat diganti atau digunakan ulang.</span></label>
    <label>Model perangkat<select required value={draft.device_model_id} disabled={!options.data} onChange={event => update("device_model_id", event.target.value)}><option value="">Pilih model katalog</option>{base && !options.data?.models.some(model => model.id === base.device_model_id) && <option value={base.device_model_id}>{base.device_model_id} (referensi existing)</option>}{options.data?.models.filter(model => model.is_active || model.id === base?.device_model_id).map(model => <option key={model.id} value={model.id}>{modelLabel(model.id, options.data)}</option>)}</select></label>
    <label>Status<select value={draft.lifecycle_status} onChange={event => update("lifecycle_status", event.target.value)}>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>Kondisi<select value={draft.condition} onChange={event => update("condition", event.target.value)}>{Object.entries(conditions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>Tanggal pembelian (opsional)<input type="date" value={draft.purchase_date} onChange={event => update("purchase_date", event.target.value)} /></label>
    <label>Waktu pemasangan (opsional)<input value={draft.installed_at} placeholder="2026-10-19T08:00:00+08:00" maxLength={64} onChange={event => update("installed_at", event.target.value)} /><span className="catalog-hint">Format ISO 8601, wajib menyertakan zona waktu.</span></label>
    <label className="catalog-wide">Catatan<textarea rows={4} maxLength={4000} value={draft.notes} onChange={event => update("notes", event.target.value)} /></label>
    </div><p className="catalog-hint">SN boleh tidak tersedia/rusak. Identifier ditambahkan di detail setelah unit tersimpan, tanpa SN palsu.</p>
    {options.error && <ErrorNotice error={options.error} retry={options.reload} />}{error && <ErrorNotice error={error} />}
    <div className="catalog-actions"><button disabled={blocked || !options.data} type="submit">{busy ? "Menyimpan…" : "Simpan aset"}</button>{onCancel && <button className="secondary" type="button" onClick={onCancel}>Batalkan</button>}{blocked && onReload && <button className="secondary" type="button" onClick={onReload}>Buang isian dan muat ulang</button>}{blocked && !base && <a className="catalog-link" href="/assets">Periksa daftar sebelum mencoba lagi</a>}</div>
  </fieldset></form>;
}
