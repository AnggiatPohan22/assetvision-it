"use client";
import { useState } from "react";
import type { Page } from "../../lib/catalog";
import type { AssetEvent } from "../../lib/assets";
import { useCatalogResource } from "../catalog/resource";
import { ErrorNotice, Pagination } from "../catalog/shared";
const names: Record<string, string> = { CREATE: "Unit dibuat", UPDATE: "Metadata diubah", ARCHIVE: "Unit diarsipkan", IDENTIFIER_ADD: "Identifier ditambahkan", IDENTIFIER_UPDATE: "Identifier diubah", IDENTIFIER_REMOVE: "Identifier dinonaktifkan" };
export default function Audit({ id, revision }: { id: string; revision: number }) {
  const [page, setPage] = useState(1);
  const resource = useCatalogResource<Page<AssetEvent>>(`/assets/${id}/events?page=${page}&page_size=10`, revision);
  return <section className="catalog-panel"><h2>Riwayat perubahan</h2>{resource.loading ? <p role="status">Memuat riwayat…</p> : resource.error ? <ErrorNotice error={resource.error} retry={resource.reload} /> : resource.data && <>
    {!resource.data.items.length && <p>Belum ada event pada halaman ini.</p>}
    {resource.data.items.map(event => <details className="asset-audit" key={event.id}><summary>{names[event.event_type] ?? event.event_type} · <time dateTime={event.recorded_at}>{event.recorded_at}</time></summary><p>Aktor: {event.actor_id}</p><div className="catalog-form-grid"><div><h3>Sebelum</h3><pre>{JSON.stringify(event.before_json, null, 2)}</pre></div><div><h3>Sesudah</h3><pre>{JSON.stringify(event.after_json, null, 2)}</pre></div></div></details>)}
    <Pagination page={resource.data.page} totalPages={resource.data.total_pages} total={resource.data.total} onPage={setPage} />
  </>}</section>;
}
