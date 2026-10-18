"use client";
import { useState } from "react";
import { canManage } from "../../lib/catalog";
import { assetMutation, conditions, errorFrom, statuses, type Asset, type Identifier } from "../../lib/assets";
import { useCatalogResource } from "../catalog/resource";
import { ConfirmButton, ErrorNotice, useCatalogRole } from "../catalog/shared";
import AssetForm from "./asset-form";
import Identifiers from "./identifiers";
import Audit from "./audit";
import { useAssetModels, modelLabel } from "./model-options";
export default function AssetDetail({ id }: { id: string }) {
  const role = useCatalogRole();
  const [revision, setRevision] = useState(0);
  const resource = useCatalogResource<Asset>(`/assets/${id}`, revision);
  const claims = useCatalogResource<Identifier[]>(`/assets/${id}/identifiers`, revision);
  const options = useAssetModels();
  const [editing, setEditing] = useState(false);
  const [claimEditing, setClaimEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState<Error>();
  const [notice, setNotice] = useState("");
  const changed = () => { setRevision(value => value + 1); setError(undefined); setBlocked(false); };
  const asset = resource.data ?? resource.previousData;
  async function archive() {
    if (!asset || busy || blocked) return;
    setBusy(true); setError(undefined);
    try { await assetMutation(`/assets/${id}/archive`, "POST", { version: asset.version }); setNotice("Unit diarsipkan; identitas dan riwayat tetap tersimpan."); changed(); }
    catch (cause) { setError(errorFrom(cause)); setBlocked(true); }
    finally { setBusy(false); }
  }
  if (!asset) return resource.error ? <ErrorNotice error={resource.error} retry={resource.reload} /> : <p role="status">Memuat aset…</p>;
  const writable = canManage(role) && !busy && !resource.loading && !resource.error && !claimEditing && !claims.loading && !claims.error;
  return <><a className="catalog-back" href="/assets">← Daftar aset</a><div className="catalog-title"><div><p className="eyebrow">UNIT FISIK</p><h1>{asset.asset_code}</h1><a className="catalog-link" href={`/catalog/models/${asset.device_model_id}`}>{modelLabel(asset.device_model_id, options.data)}</a></div><span className="catalog-status archived">{statuses[asset.lifecycle_status]}</span></div>
    {notice && <p className="catalog-success" role="status">{notice}</p>}{resource.error && <ErrorNotice error={resource.error} retry={resource.reload} />}{options.error && <ErrorNotice error={options.error} retry={options.reload} />}{error && <ErrorNotice error={error} />}
    {blocked && <button className="secondary" onClick={changed}>Muat ulang data aset</button>}
    {!editing && canManage(role) && <div className="catalog-actions catalog-detail-actions"><button disabled={!writable || blocked} onClick={() => setEditing(true)}>Edit aset</button>{asset.lifecycle_status !== "ARCHIVED" && <ConfirmButton label="Arsipkan aset" title="Arsipkan unit ini?" disabled={!writable || blocked} onConfirm={() => void archive()}>Asset ID tetap dicadangkan. Tidak ada data yang dihapus.</ConfirmButton>}</div>}
    {editing ? <AssetForm initial={asset} onSaved={() => { setEditing(false); setNotice("Metadata tersimpan."); changed(); }} onCancel={() => { setEditing(false); changed(); }} onReload={() => { setEditing(false); changed(); }} /> : <section className="catalog-panel catalog-summary"><h2>Metadata unit</h2><dl><div><dt>Asset ID permanen</dt><dd>{asset.asset_code}</dd></div><div><dt>UUID</dt><dd>{asset.id}</dd></div><div><dt>Kondisi</dt><dd>{conditions[asset.condition]}</dd></div><div><dt>Versi</dt><dd>{asset.version}</dd></div><div><dt>Tanggal pembelian</dt><dd>{asset.purchase_date ?? "Belum diisi"}</dd></div><div><dt>Waktu pemasangan</dt><dd>{asset.installed_at ?? "Belum diisi"}</dd></div><div><dt>Dibuat</dt><dd>{asset.created_at}</dd></div><div><dt>Diperbarui</dt><dd>{asset.updated_at}</dd></div><div className="catalog-wide"><dt>Catatan</dt><dd className="catalog-preserve">{asset.notes ?? "Belum ada catatan"}</dd></div></dl></section>}
    {claims.loading ? <p role="status">Memuat identifier…</p> : claims.error ? <ErrorNotice error={claims.error} retry={claims.reload} /> : claims.data && <Identifiers asset={asset} items={claims.data} editable={canManage(role) && !editing && !busy && !resource.loading && !resource.error && !blocked} onEditing={setClaimEditing} onChanged={changed} />}
    <Audit id={id} revision={revision} />
  </>;
}
