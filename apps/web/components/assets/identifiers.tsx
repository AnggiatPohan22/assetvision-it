"use client";
import { useRef, useState, type FormEvent } from "react";
import { CatalogError } from "../../lib/catalog";
import { assetMutation, boundedJson, errorFrom, identifierTypes, sources, validateIdentifier, verifications, type Asset, type Identifier, type IdentifierResult } from "../../lib/assets";
import { ConfirmButton, ErrorNotice } from "../catalog/shared";

function IdentifierForm({ asset, initial, onDone, onCancel }: { asset: Asset; initial?: Identifier; onDone: () => void; onCancel: () => void }) {
  const [base] = useState({ asset, initial });
  const [type, setType] = useState<Identifier["identifier_type"]>(initial?.identifier_type ?? "SERIAL_NUMBER");
  const [raw, setRaw] = useState(initial?.raw_value ?? "");
  const [source, setSource] = useState<Identifier["source"]>(initial?.source ?? "MANUAL");
  const [verification, setVerification] = useState<Identifier["verification_status"]>(initial?.verification_status ?? "UNVERIFIED");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<Error>();
  async function save(event: FormEvent) {
    event.preventDefault(); if (lock.current || blocked) return;
    lock.current = true; setBusy(true); setError(undefined);
    try {
      validateIdentifier(type, raw);
      const payload = { asset_version: base.asset.version, ...(base.initial ? { version: base.initial.version } : {}), identifier_type: type, raw_value: raw, source, verification_status: verification, notes: notes || null };
      if (notes.length > 4000) throw new Error("Catatan maksimal 4000 karakter.");
      boundedJson(payload);
      await assetMutation<IdentifierResult>(`/assets/${asset.id}/identifiers${base.initial ? `/${base.initial.id}` : ""}`, base.initial ? "PATCH" : "POST", payload);
      onDone();
    } catch (cause) { const failure = errorFrom(cause); setError(failure); if (failure instanceof CatalogError && (failure.status === 409 || failure.status >= 500)) setBlocked(true); }
    finally { lock.current = false; setBusy(false); }
  }
  return <form className="catalog-panel" aria-label="Form identifier" onSubmit={save}><fieldset disabled={busy}><legend>{initial ? "Edit identifier" : "Tambah identifier"}</legend><div className="catalog-form-grid">
    <label>Jenis identifier<select value={type} onChange={event => setType(event.target.value as typeof type)}>{Object.entries(identifierTypes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>Nilai bukti<input required maxLength={255} value={raw} onChange={event => setRaw(event.target.value)} /></label>
    <label>Sumber<select value={source} onChange={event => setSource(event.target.value as typeof source)}>{Object.entries(sources).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>Verifikasi<select value={verification} onChange={event => setVerification(event.target.value as typeof verification)}>{Object.entries(verifications).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label className="catalog-wide">Catatan identifier<textarea maxLength={4000} value={notes} onChange={event => setNotes(event.target.value)} /></label></div>
    {error && <ErrorNotice error={error} />}<div className="catalog-actions"><button disabled={blocked} type="submit">Simpan identifier</button><button type="button" className="secondary" onClick={onCancel}>Batalkan dan muat ulang</button></div>
  </fieldset></form>;
}

export default function Identifiers({ asset, items, editable, onChanged, onEditing }: { asset: Asset; items: Identifier[]; editable: boolean; onChanged: () => void; onEditing: (editing: boolean) => void }) {
  const [edit, setEdit] = useState<Identifier | "new">();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const [blocked, setBlocked] = useState(false);
  const lock = useRef(false);
  function done() { setEdit(undefined); onEditing(false); onChanged(); }
  function start(value: Identifier | "new") { setEdit(value); onEditing(true); }
  async function remove(item: Identifier) {
    if (lock.current || blocked) return;
    lock.current = true; setBusy(true); setError(undefined); onEditing(true);
    try {
      await assetMutation<IdentifierResult>(`/assets/${asset.id}/identifiers/${item.id}?version=${item.version}&asset_version=${asset.version}`, "DELETE");
      done();
    } catch (cause) { setError(errorFrom(cause)); setBlocked(true); }
    finally { lock.current = false; setBusy(false); onEditing(false); }
  }
  return <section className="catalog-panel"><div className="catalog-section-heading"><h2>Identifier unit</h2>{editable && !edit && <button disabled={busy || blocked} onClick={() => start("new")}>Tambah identifier</button>}</div>
    {!items.some(item => item.identifier_type === "SERIAL_NUMBER") && <p className="catalog-notice">SN tidak tersedia / label rusak. Tidak ada SN palsu yang dibuat.</p>}
    {error && <ErrorNotice error={error} />}{blocked && <button className="secondary" onClick={() => { setBlocked(false); onChanged(); }}>Muat ulang identifier</button>}
    {items.map(item => <article className="asset-identifier" key={item.id}><h3>{identifierTypes[item.identifier_type]} · {item.normalized_value}</h3><p className="catalog-preserve">Bukti: {item.raw_value}</p><p>{sources[item.source]} · {verifications[item.verification_status]}</p>{item.notes && <p className="catalog-preserve">{item.notes}</p>}
      {!!item.collision_asset_ids.length && <div className="catalog-notice">Benturan klaim dengan unit lain: {item.collision_asset_ids.map(id => <a className="catalog-link asset-collision" key={id} href={`/assets/${id}`}>{id}</a>)}<p>Tinjau bukti; unit tidak digabung atau ditimpa.</p></div>}
      {editable && !edit && <div className="catalog-actions"><button className="secondary" disabled={busy || blocked} onClick={() => start(item)}>Edit identifier</button><ConfirmButton label="Hapus identifier" title="Hapus klaim aktif?" disabled={busy || blocked} onConfirm={() => void remove(item)}>Klaim akan dinonaktifkan. Riwayat audit tetap tersimpan.</ConfirmButton></div>}
    </article>)}
    {edit && <IdentifierForm asset={asset} initial={edit === "new" ? undefined : edit} onDone={done} onCancel={done} />}
  </section>;
}
