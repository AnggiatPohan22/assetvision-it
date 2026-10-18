"use client";
import { useState, type FormEvent } from "react";
import { canManage, type Page } from "../../lib/catalog";
import { assetQuery, statuses, conditions, type Asset } from "../../lib/assets";
import { useCatalogResource } from "../catalog/resource";
import { ErrorNotice, Empty, Pagination, useCatalogRole } from "../catalog/shared";
import { modelLabel, useAssetModels } from "./model-options";
export default function AssetList() {
  const role = useCatalogRole();
  const options = useAssetModels();
  const [filters, setFilters] = useState({ search: "", model: "", status: "", page: 1 });
  const resource = useCatalogResource<Page<Asset>>(assetQuery(filters));
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    setFilters({ search: String(data.get("search") ?? ""), model: String(data.get("model") ?? ""), status: String(data.get("status") ?? ""), page: 1 });
  }
  return <><div className="catalog-title"><div><p className="eyebrow">REGISTRY UNIT FISIK</p><h1>Aset fisik</h1><p className="muted">Satu model, banyak unit. Setiap Asset ID bersifat permanen.</p></div>{canManage(role) && <div className="catalog-actions"><a className="secondary" href="/assets/import">Impor CSV</a><a className="catalog-button" href="/assets/new">+ Tambah aset</a></div>}</div>
    <form className="catalog-filters catalog-panel" aria-label="Filter aset" onSubmit={apply}>
      <label>Cari Asset ID / SN / MAC<input name="search" type="search" maxLength={200} placeholder="Kode aset atau identifier" /></label>
      <label>Model<select name="model" disabled={!options.data}><option value="">Semua model</option>{options.data?.models.map(model => <option key={model.id} value={model.id}>{modelLabel(model.id, options.data)}</option>)}</select></label>
      <label>Status<select name="status"><option value="">Semua status</option>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><button type="submit">Terapkan</button>
    </form>{options.error && <ErrorNotice error={options.error} retry={options.reload} />}
    {canManage(role) && <p><a className="catalog-link" href={`/api/v1${assetQuery(filters, true)}`}>Unduh CSV sesuai filter</a><span className="catalog-hint">Semua halaman. Ekspor adalah laporan, bukan template impor.</span></p>}
    {resource.loading ? <p role="status">Memuat aset…</p> : resource.error ? <ErrorNotice error={resource.error} retry={resource.reload} /> : resource.data && <>
      {!resource.data.items.length ? <Empty><h2>{resource.data.total ? "Halaman ini kosong" : "Belum ada aset yang sesuai"}</h2><p>Ubah filter atau tambahkan unit bila Anda administrator.</p></Empty> : <div className="catalog-table-wrap"><table className="catalog-table"><caption className="sr-only">Daftar aset fisik</caption><thead><tr><th>Asset ID</th><th>Model</th><th>Status</th><th>Kondisi</th></tr></thead><tbody>{resource.data.items.map(asset => <tr key={asset.id}><td><a className="catalog-model-name" href={`/assets/${asset.id}`}>{asset.asset_code}</a></td><td>{modelLabel(asset.device_model_id, options.data)}</td><td>{statuses[asset.lifecycle_status]}</td><td>{conditions[asset.condition]}</td></tr>)}</tbody></table></div>}
      <Pagination page={resource.data.page} totalPages={resource.data.total_pages} total={resource.data.total} onPage={page => setFilters(old => ({ ...old, page }))} />
    </>}
  </>;
}
