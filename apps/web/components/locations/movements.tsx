"use client";
import { useState } from "react";
import type { Asset } from "../../lib/assets";
import type { Page } from "../../lib/catalog";
import { eventNames, locationName, movementNames, reasonValue, type Location, type Movement, type TimelineEvent, type Tree } from "../../lib/locations";
import { useCatalogResource } from "../catalog/resource";
import { ErrorNotice, Pagination, useCatalogRole, useCatalogUserId } from "../catalog/shared";
import { WriteForm } from "./shared";

function Decision({ movement, items, onDone }: { movement:Movement; items:Location[]; onDone:()=>void }) {
  const role=useCatalogRole(); const [snapshot]=useState(movement); const [reason,setReason]=useState("");
  const [action,setAction]=useState(role==="ADMIN"?"approve":"cancel");
  const current=useCatalogResource<Asset & {current_location_id:string|null}>(`/assets/${snapshot.asset_id}`);
  const history=useCatalogResource<Page<TimelineEvent>>(`/assets/${snapshot.asset_id}/timeline?page_size=5`);
  const stale=!!current.data&&(current.data.version!==snapshot.expected_asset_version||current.data.current_location_id!==snapshot.from_location_id);
  const ineligible=current.data?.lifecycle_status==="ARCHIVED" || !items.some(item=>item.id===snapshot.to_location_id&&item.is_active);
  return <WriteForm title="Review perpindahan" submitLabel="Konfirmasi keputusan" onSaved={onDone} onCancel={onDone} disabled={current.loading||!!current.error||history.loading||!!history.error} prepare={()=>{
    if(action==="approve"&&(stale||ineligible)) throw new Error("Request sudah stale. Tolak atau batalkan, lalu ajukan ulang setelah review.");
    return {path:`/movements/${snapshot.id}/${action}`,method:"POST",body:{version:snapshot.version,reason:reasonValue(reason)}};
  }}>
    <p><a className="catalog-link" href={`/assets/${snapshot.asset_id}`}>Buka detail aset dan seluruh timeline</a></p>
    {current.data&&<h4>Aset {current.data.asset_code}</h4>}
    <p>Snapshot request: {snapshot.request_snapshot_json.from?.name??"Belum ditempatkan"} → {snapshot.request_snapshot_json.to.name}</p>
    <p>Alasan request: {snapshot.reason}</p><p>Pemohon: {snapshot.requested_by} · {snapshot.requested_at}</p>
    {current.error&&<ErrorNotice error={current.error}/>}{history.error&&<ErrorNotice error={history.error}/>}
    {current.data&&<p>Lokasi resmi saat review: {locationName(current.data.current_location_id,items)} · versi {current.data.version} (request memakai {snapshot.expected_asset_version})</p>}
    {stale&&<p className="catalog-notice" role="status">Request stale. Approval tidak tersedia; tutup request dan ajukan ulang setelah review.</p>}
    {ineligible&&<p className="catalog-notice">Aset atau tujuan tidak memenuhi syarat approval. Periksa arsip/status sebelum melanjutkan.</p>}
    {role==="ADMIN"&&<p className="catalog-hint">Pilot: ADMIN boleh menyetujui request sendiri; pemohon dan peninjau tetap dicatat.</p>}
    {history.data&&<details><summary>Riwayat terbaru ({history.data.items.length})</summary><ol>{history.data.items.map(item=><li key={`${item.source}:${item.id}`}>{eventNames[item.event_type]??item.event_type} · {item.occurred_at} · {item.actor_id}</li>)}</ol></details>}
    <label>Keputusan<select value={action} onChange={event=>setAction(event.target.value)}>{role==="ADMIN"&&<><option value="approve" disabled={stale||ineligible}>Setujui perpindahan</option><option value="reject">Tolak perpindahan</option></>}<option value="cancel">Batalkan request</option></select></label>
    <label>Alasan keputusan<textarea required maxLength={2000} value={reason} onChange={event=>setReason(event.target.value)}/></label>
    <p className="catalog-hint">Hanya persetujuan yang mengubah lokasi resmi. Keputusan tersimpan bersama aktor dan waktu.</p>
  </WriteForm>;
}
export function MovementList({ items, locations, onChanged, writable=true }: { items:Movement[]; locations:Location[]; onChanged:()=>void; writable?:boolean }) {
  const role=useCatalogRole(); const actor=useCatalogUserId(); const [selected,setSelected]=useState<Movement>();
  const done=()=>{setSelected(undefined);onChanged();};
  return <>{selected&&<Decision key={selected.id} movement={selected} items={locations} onDone={done}/>}
    {!items.length?<p>Belum ada request perpindahan sesuai filter.</p>:<ul className="location-records">{items.map(item=><li key={item.id}><div className="catalog-section-heading"><h3>{movementNames[item.status]}</h3><a className="catalog-link" href={`/assets/${item.asset_id}`}>Detail aset</a></div>
      <p>{item.request_snapshot_json.from?.name??"Belum ditempatkan"} → {item.request_snapshot_json.to.name}</p><p>{item.reason}</p>
      <p className="catalog-hint">Pemohon {item.requested_by} · {item.requested_at}</p>
      {item.reviewed_at&&<p className="catalog-hint">Peninjau {item.reviewed_by} · {item.reviewed_at} · {item.review_reason}</p>}
      {item.status==="PENDING"&&(role==="ADMIN"||(role==="OFFICER"&&actor===item.requested_by))&&<button type="button" className="secondary" disabled={!writable||!!selected} onClick={()=>setSelected(item)}>{role==="ADMIN"?"Review request":"Batalkan request saya"}</button>}
    </li>)}</ul>}</>;
}
export default function MovementInbox() {
  const [status,setStatus]=useState("PENDING"); const [page,setPage]=useState(1); const [revision,setRevision]=useState(0);
  const resource=useCatalogResource<Page<Movement>>(`/movements?page_size=10&page=${page}${status?`&status=${status}`:""}`,revision);
  const tree=useCatalogResource<Tree>("/locations/tree",revision);
  const reload=()=>{setRevision(value=>value+1);};
  return <><div className="catalog-title"><div><p className="eyebrow">ADMIN / PERPINDAHAN</p><h1>Inbox perpindahan</h1><p className="muted">Bandingkan request dengan lokasi resmi dan riwayat sebelum mengambil keputusan.</p></div></div>
    <label>Status request<select value={status} onChange={event=>{setStatus(event.target.value);setPage(1);}}><option value="">Semua status</option>{Object.entries(movementNames).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
    <button className="secondary" onClick={reload}>Muat ulang inbox</button>
    {resource.loading||tree.loading?<p role="status">Memuat inbox perpindahan…</p>:resource.error||tree.error?<ErrorNotice error={(resource.error||tree.error)!} retry={reload}/>:resource.data&&tree.data&&<section className="catalog-panel"><MovementList key={`${revision}:${page}:${status}`} items={resource.data.items} locations={tree.data.items} onChanged={reload}/><Pagination page={page} totalPages={resource.data.total_pages} total={resource.data.total} onPage={setPage}/></section>}
  </>;
}
