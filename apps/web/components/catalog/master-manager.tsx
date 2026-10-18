"use client";
import { useState, type FormEvent } from "react";
import { canManage, catalogMutation, type Category, type Manufacturer, type Page } from "../../lib/catalog";
import { useCatalogResource } from "./resource";
import { Empty, ErrorNotice, Loading, Pagination, Status, useCatalogRole } from "./shared";

function MasterSection({ kind }: { kind: "device-categories" | "manufacturers" }) {
  const category = kind === "device-categories";
  const title = category ? "Kategori" : "Produsen";
  const [page, setPage] = useState(1);
  const resource = useCatalogResource<Page<Category | Manufacturer>>(`/${kind}?page=${page}&page_size=10`);
  const [editing, setEditing] = useState<Category | Manufacturer>();
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<Error>();
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  function start(record?: Category | Manufacturer) { setEditing(record); setRevision(value => value + 1); setError(undefined); setNotice(""); }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const name = String(values.get("name") ?? "").trim().replace(/\s+/g, " ");
    const code = String(values.get("code") ?? "").trim().toLowerCase();
    const website = String(values.get("website") ?? "").trim();
    setError(undefined); setNotice("");
    try {
      if (!name) throw new Error("Nama wajib diisi.");
      if (category && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(code)) throw new Error("Kode memakai huruf kecil/angka dan tanda hubung, tanpa spasi.");
      if (!category && website) { const url = new URL(website); if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) throw new Error("Gunakan URL http/https tanpa kredensial."); }
      setBusy(true);
      await catalogMutation(`/${kind}${editing ? `/${editing.id}` : ""}`, editing ? "PATCH" : "POST", {
        name, is_active: values.get("is_active") === "on", ...(category ? { code, description: String(values.get("description") ?? "") || null } : { website: website || null }),
        ...(editing ? { version: editing.version } : {}),
      });
      setEditing(undefined); setRevision(value => value + 1); resource.reload(); setNotice(`${title} berhasil disimpan.`);
    } catch (cause) { setError(cause instanceof Error ? cause : new Error("Data belum dapat disimpan.")); }
    finally { setBusy(false); }
  }
  return <section className="catalog-master-section"><div className="catalog-section-heading"><h2>{title}</h2><button type="button" className="secondary" disabled={busy} onClick={() => start()}>Tambah {title.toLowerCase()}</button></div>
    {notice && <p className="catalog-success" role="status">{notice}</p>}
    <form key={revision} className="catalog-panel" aria-label={`Form ${title.toLowerCase()}`} onSubmit={save}><fieldset disabled={busy}><legend>{editing ? `Edit ${title.toLowerCase()}` : `${title} baru`}</legend>
      <label>Nama {title.toLowerCase()} *<input name="name" required maxLength={category ? 100 : 150} defaultValue={editing?.name ?? ""} /></label>
      {category ? <><label>Kode kategori *<input name="code" required maxLength={50} defaultValue={editing && "code" in editing ? editing.code : ""} placeholder="misalnya: access-point" /></label><label>Deskripsi kategori<textarea name="description" rows={2} maxLength={4000} defaultValue={editing && "description" in editing ? editing.description ?? "" : ""} /></label></>
        : <label>Website produsen<input name="website" type="url" maxLength={2048} defaultValue={editing && "website" in editing ? editing.website ?? "" : ""} placeholder="https://…" /></label>}
      <label className="catalog-check"><input type="checkbox" name="is_active" defaultChecked={editing?.is_active ?? true} />{title} aktif</label>
      <div className="catalog-actions"><button type="submit">{busy ? "Menyimpan…" : `Simpan ${title.toLowerCase()}`}</button>{editing && <button type="button" className="secondary" onClick={() => start()}>Batalkan edit</button>}</div></fieldset>
      {error && <><ErrorNotice error={error} /><button type="button" className="secondary" onClick={() => { start(); resource.reload(); }}>Muat ulang dan buang isian</button></>}
    </form>
    {resource.loading ? <Loading /> : resource.error ? <ErrorNotice error={resource.error} retry={resource.reload} /> : resource.data && <>
      {resource.data.items.length ? <div className="catalog-table-wrap"><table className="catalog-table"><caption className="sr-only">Daftar {title.toLowerCase()}</caption><thead><tr><th scope="col">Nama</th><th scope="col">Status</th><th scope="col">Aksi</th></tr></thead><tbody>{resource.data.items.map(record => <tr key={record.id}><td>{record.name}{"code" in record && <span className="catalog-subtitle">{record.code}</span>}</td><td><Status active={record.is_active} /></td><td><button type="button" className="secondary" disabled={busy} aria-label={`Edit ${record.name}`} onClick={() => start(record)}>Edit</button></td></tr>)}</tbody></table></div> : <Empty><p>Belum ada {title.toLowerCase()}.</p></Empty>}
      <Pagination page={page} totalPages={resource.data.total_pages} total={resource.data.total} onPage={setPage} />
    </>}
  </section>;
}
export default function MasterManager() {
  const role = useCatalogRole();
  if (!canManage(role)) return <p>Hanya administrator yang dapat mengelola kategori dan produsen.</p>;
  return <><div className="catalog-title"><div><p className="eyebrow">PENGATURAN KATALOG</p><h1>Kategori & produsen</h1><p className="muted">Nonaktifkan referensi tanpa menghapus model atau riwayatnya.</p></div></div><div className="catalog-master-grid"><MasterSection kind="device-categories" /><MasterSection kind="manufacturers" /></div></>;
}
