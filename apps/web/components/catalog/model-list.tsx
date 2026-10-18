"use client";
import { useState, type FormEvent } from "react";
import { canManage, environmentNames, modelQuery, type DeviceModel, type Page } from "../../lib/catalog";
import { useCatalogOptions } from "./options";
import { useCatalogResource } from "./resource";
import { Empty, ErrorNotice, Loading, Pagination, Status, useCatalogRole } from "./shared";

export default function ModelList() {
  const role = useCatalogRole();
  const options = useCatalogOptions();
  const [filters, setFilters] = useState({ search: "", category: "", manufacturer: "", status: "all", page: 1 });
  const resource = useCatalogResource<Page<DeviceModel>>(modelQuery(filters));
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setFilters({ search: String(data.get("search") ?? ""), category: String(data.get("category") ?? ""), manufacturer: String(data.get("manufacturer") ?? ""), status: String(data.get("status") ?? "all"), page: 1 });
  }
  const categories = new Map(options.categories?.map(item => [item.id, item.name]));
  const manufacturers = new Map(options.manufacturers?.map(item => [item.id, item.name]));
  return <><div className="catalog-title"><div><p className="eyebrow">KATALOG PERANGKAT</p><h1>Model perangkat</h1><p className="muted">Referensi model, spesifikasi, dan foto dalam satu katalog.</p></div>
    {canManage(role) && <a href="/catalog/models/new" className="catalog-button">+ Tambah model</a>}</div>
    <form className="catalog-filters catalog-panel" onSubmit={apply} aria-label="Filter model">
      <label>Cari model<input name="search" type="search" maxLength={200} placeholder="Nama, alias, atau produsen" defaultValue="" /></label>
      <label>Kategori<select name="category" disabled={!options.categories}><option value="">Semua kategori</option>{options.categories?.map(item => <option key={item.id} value={item.id}>{item.name}{!item.is_active ? " (arsip)" : ""}</option>)}</select></label>
      <label>Produsen<select name="manufacturer" disabled={!options.manufacturers}><option value="">Semua produsen</option>{options.manufacturers?.map(item => <option key={item.id} value={item.id}>{item.name}{!item.is_active ? " (arsip)" : ""}</option>)}</select></label>
      <label>Status<select name="status"><option value="all">Semua status</option><option value="true">Aktif</option><option value="false">Diarsipkan</option></select></label>
      <button type="submit">Terapkan</button>
    </form>
    {options.error && <ErrorNotice error={options.error} retry={options.reload} />}
    {resource.loading ? <Loading /> : resource.error ? <ErrorNotice error={resource.error} retry={resource.reload} /> : resource.data && <>
      {resource.data.items.length === 0 ? <Empty><h2>{resource.data.total ? "Halaman ini kosong" : "Belum ada model yang sesuai"}</h2><p>Ubah pencarian/filter, atau tambahkan model pertama bila Anda administrator.</p></Empty>
        : <div className="catalog-table-wrap"><table className="catalog-table"><caption className="sr-only">Daftar model perangkat</caption><thead><tr><th scope="col">Model</th><th scope="col">Kategori</th><th scope="col">Lingkungan</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Detail</span></th></tr></thead>
          <tbody>{resource.data.items.map(model => <tr key={model.id}><td><a href={`/catalog/models/${model.id}`} className="catalog-model-name">{model.model_name}</a><span className="catalog-subtitle">{manufacturers.get(model.manufacturer_id) ?? "Produsen belum dimuat"}</span></td>
            <td>{categories.get(model.category_id) ?? "Kategori belum dimuat"}</td><td>{environmentNames[model.environment]}</td><td><Status active={model.is_active} /></td><td><a className="catalog-link" href={`/catalog/models/${model.id}`} aria-label={`Lihat detail ${model.model_name}`}>Lihat detail →</a></td></tr>)}</tbody></table></div>}
      <Pagination page={resource.data.page} totalPages={resource.data.total_pages} total={resource.data.total} onPage={page => setFilters(old => ({ ...old, page }))} />
    </>}
  </>;
}
