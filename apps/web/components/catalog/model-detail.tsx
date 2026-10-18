"use client";
import { useState } from "react";
import { canManage, catalogMutation, environmentNames, type DeviceModel } from "../../lib/catalog";
import { useCatalogResource } from "./resource";
import { useCatalogOptions } from "./options";
import { ConfirmButton, ErrorNotice, Loading, Status, useCatalogRole } from "./shared";
import ModelForm from "./model-form";
import Gallery from "./gallery";

export default function ModelDetail({ id }: { id: string }) {
  const role = useCatalogRole();
  const resource = useCatalogResource<DeviceModel>(`/device-models/${id}`);
  const options = useCatalogOptions();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const [notice, setNotice] = useState("");
  const [editRevision, setEditRevision] = useState(0);
  const currentModel = resource.data ?? resource.previousData;
  if (!currentModel && resource.error) return <ErrorNotice error={resource.error} retry={resource.reload} />;
  if (!currentModel) return <Loading />;
  const model = currentModel;
  const reload = () => { setError(undefined); resource.reload(); };
  async function changeStatus() {
    if (busy) return;
    setBusy(true); setError(undefined);
    try {
      await catalogMutation(`/device-models/${id}${model.is_active ? "/archive" : ""}`, model.is_active ? "POST" : "PATCH", { version: model.version, ...(!model.is_active ? { is_active: true } : {}) });
      setNotice(model.is_active ? "Model telah diarsipkan. Referensi tetap tersimpan." : "Model kembali aktif."); resource.reload();
    } catch (cause) { setError(cause instanceof Error ? cause : new Error("Status model belum dapat diubah.")); }
    finally { setBusy(false); }
  }
  return <><a className="catalog-back" href="/catalog/models">← Semua model</a><div className="catalog-title"><div><p className="eyebrow">DETAIL MODEL</p><h1>{model.model_name}</h1><p className="muted">{options.manufacturers?.find(item => item.id === model.manufacturer_id)?.name ?? "Produsen sedang dimuat"} <span className="catalog-dot">/</span> {options.categories?.find(item => item.id === model.category_id)?.name ?? "Kategori sedang dimuat"}</p></div><Status active={model.is_active} /></div>
    {notice && <p className="catalog-success" role="status">{notice}</p>}{error && <ErrorNotice error={error} retry={reload} />}
    {resource.error && <ErrorNotice error={resource.error} retry={resource.reload} />}
    {options.error && <ErrorNotice error={options.error} retry={options.reload} />}
    {canManage(role) && !editing && <div className="catalog-actions catalog-detail-actions"><button type="button" disabled={busy} onClick={() => { setError(undefined); setEditing(true); }}>Edit model</button><ConfirmButton label={model.is_active ? "Arsipkan model" : "Pulihkan model"} title={model.is_active ? "Arsipkan model?" : "Pulihkan model?"} disabled={busy} onConfirm={() => void changeStatus()}>{model.is_active ? "Model tidak lagi aktif. Detail dan foto referensinya tetap tersimpan." : "Model akan diaktifkan kembali. Kategori dan produsennya harus aktif."}</ConfirmButton></div>}
    {editing ? <ModelForm key={editRevision} initial={model} onSaved={() => { setEditing(false); setNotice("Perubahan model tersimpan."); resource.reload(); }} onCancel={() => setEditing(false)} onReload={() => { setEditing(false); setEditRevision(value => value + 1); resource.reload(); }} />
      : <section className="catalog-panel catalog-summary"><h2>Informasi model</h2><dl><div><dt>Lingkungan</dt><dd>{environmentNames[model.environment]}</dd></div><div><dt>Nama alternatif</dt><dd>{model.aliases.join(", ") || "Belum ditambahkan"}</dd></div><div className="catalog-wide"><dt>Deskripsi</dt><dd className="catalog-preserve">{model.description || "Belum ada deskripsi."}</dd></div></dl>
        {Object.keys(model.specs).length > 0 && <><h3>Spesifikasi</h3><dl>{Object.entries(model.specs).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{(Array.isArray(value) ? value : [value]).map(item => item === null ? "Kosong" : typeof item === "boolean" ? item ? "Ya" : "Tidak" : String(item)).join(", ")}</dd></div>)}</dl></>}
      </section>}
    <Gallery key={model.id} model={model} editable={canManage(role) && !editing} onChanged={() => { resource.reload(); }} onBusy={setBusy} />
  </>;
}
