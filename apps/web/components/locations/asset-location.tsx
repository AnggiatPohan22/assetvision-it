"use client";
import { useState } from "react";
import type { Asset } from "../../lib/assets";
import type { Page } from "../../lib/catalog";
import { canObserve, eventNames, locationName, reasonValue, reviewNames, statusNames, type Location, type LocationStatus, type Movement, type Observation, type TimelineEvent, type Tree } from "../../lib/locations";
import { useCatalogResource } from "../catalog/resource";
import { ErrorNotice, Pagination, useCatalogRole } from "../catalog/shared";
import { MovementList } from "./movements";
import { LocationSelect, WriteForm } from "./shared";

function EvidenceForm({ asset, status, locations, mode, onDone }: { asset:Asset; status:LocationStatus; locations:Location[]; mode:string; onDone:()=>void }) {
  const [snapshot]=useState(status); const [destination,setDestination]=useState(""); const [reason,setReason]=useState(""); const [observedAt,setObservedAt]=useState("");
  const observation=mode==="observe";
  return <WriteForm title={observation?"Catat observasi lokasi":mode==="initial"?"Penempatan awal":"Ajukan perpindahan"} submitLabel={observation?"Simpan observasi":mode==="initial"?"Konfirmasi penempatan":"Kirim request"} onSaved={onDone} onCancel={onDone} prepare={()=>{
    if(!destination) throw new Error("Pilih lokasi aktif terlebih dahulu.");
    const note=reasonValue(reason);
    if(observation) {
      if(observedAt&&(!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(observedAt)||!Number.isFinite(Date.parse(observedAt))||Date.parse(observedAt)>Date.now())) throw new Error("Waktu observasi harus ISO 8601 dengan zona waktu dan tidak di masa depan.");
      return {path:"/location-observations",method:"POST",body:{asset_id:asset.id,asset_version:snapshot.asset_version,observed_location_id:destination,evidence_note:note,...(observedAt?{observed_at:observedAt}:{})}};
    }
    if(mode==="initial") return {path:`/assets/${asset.id}/initial-placement`,method:"POST",body:{version:snapshot.asset_version,location_id:destination,reason:note}};
    return {path:`/assets/${asset.id}/movements`,method:"POST",body:{asset_version:snapshot.asset_version,to_location_id:destination,reason:note}};
  }}>
    <p>Lokasi resmi saat formulir dibuka: {locationName(snapshot.current_location_id,locations)} · versi {snapshot.asset_version}</p>
    <LocationSelect items={locations} value={destination} onChange={setDestination} exclude={mode==="move"?snapshot.current_location_id??undefined:undefined} label={observation?"Lokasi yang diamati":"Lokasi tujuan"}/>
    <label>{observation?"Bukti / catatan observasi":"Alasan perpindahan / penempatan"}<textarea required maxLength={2000} value={reason} onChange={event=>setReason(event.target.value)}/></label>
    {observation&&<label>Waktu observasi (opsional)<input value={observedAt} onChange={event=>setObservedAt(event.target.value)} placeholder="2026-10-19T08:00:00+08:00"/><span className="catalog-hint">Kosong memakai waktu server. Observasi adalah bukti; tidak mengubah lokasi resmi.</span></label>}
    {!observation&&<p className="catalog-notice">{mode==="initial"?"Keputusan ADMIN ini menetapkan lokasi awal dan mencatat verifikasi. Periksa tujuan sebelum konfirmasi.":"Request belum memindahkan aset. Lokasi resmi berubah hanya setelah approval ADMIN."}</p>}
  </WriteForm>;
}
function ReviewObservation({ item, onDone }: { item:Observation; onDone:()=>void }) {
  const [snapshot]=useState(item); const [review,setReview]=useState("ACKNOWLEDGED"); const [reason,setReason]=useState("");
  return <WriteForm title="Review observasi" submitLabel="Konfirmasi review observasi" onSaved={onDone} onCancel={onDone} prepare={()=>({path:`/location-observations/${snapshot.id}/review`,method:"POST",body:{version:snapshot.version,review_status:review,reason:reasonValue(reason)}})}>
    <p>{snapshot.evidence_note} · {snapshot.snapshot_json.observed_location.name} · {snapshot.observed_at}</p>
    <label>Hasil review<select value={review} onChange={event=>setReview(event.target.value)}><option value="ACKNOWLEDGED">Sudah ditinjau (tetap bukti aktif)</option><option value="DISMISSED">Kesampingkan dari status terkini</option></select></label>
    <label>Alasan review<textarea required maxLength={2000} value={reason} onChange={event=>setReason(event.target.value)}/></label>
    <p className="catalog-hint">Review tidak memindahkan aset. Menandai sudah ditinjau tidak menghapus konflik; kesampingkan tetap menyimpan riwayat.</p>
  </WriteForm>;
}
function ObservationHistory({ id, revision, onChanged }: { id:string; revision:number; onChanged:()=>void }) {
  const role=useCatalogRole(); const [page,setPage]=useState(1); const [selected,setSelected]=useState<Observation>();
  const resource=useCatalogResource<Page<Observation>>(`/assets/${id}/location-observations?page_size=5&page=${page}`,revision);
  const done=()=>{setSelected(undefined);onChanged();};
  return <section className="catalog-panel"><h2>Bukti observasi</h2>{selected&&<ReviewObservation key={selected.id} item={selected} onDone={done}/>}
    {resource.loading?<p role="status">Memuat observasi…</p>:resource.error?<ErrorNotice error={resource.error} retry={resource.reload}/>:<>
    {!(resource.data?.items??[]).length?<p>Belum ada observasi.</p>:<ul className="location-records">{resource.data!.items.map(item=><li key={item.id}><h3>{item.snapshot_json.observed_location.name}</h3><p>{item.evidence_note}</p><p>{reviewNames[item.review_status]} · {statusNames[item.comparison_status]??item.comparison_status}</p><p className="catalog-hint">Pengamat {item.observed_by} · Diamati {item.observed_at} · Direkam {item.recorded_at}</p>{item.reviewed_at&&<p className="catalog-hint">Review {item.reviewed_by} · {item.reviewed_at} · {item.review_reason}</p>}{role==="ADMIN"&&item.review_status==="PENDING"&&<button className="secondary" disabled={!!selected} onClick={()=>setSelected(item)}>Review observasi</button>}</li>)}</ul>}
    {resource.data?.items&&<Pagination page={page} totalPages={resource.data.total_pages} total={resource.data.total} onPage={setPage}/>}</>}
  </section>;
}
function Timeline({ id, revision }: { id:string; revision:number }) {
  const [page,setPage]=useState(1); const [source,setSource]=useState("");
  const resource=useCatalogResource<Page<TimelineEvent>>(`/assets/${id}/timeline?page_size=10&page=${page}${source?`&source=${source}`:""}`,revision);
  return <section className="catalog-panel"><h2>Timeline aset</h2><p className="catalog-hint">Riwayat immutable, diurutkan waktu kejadian terbaru. Koreksi dicatat sebagai bukti baru.</p>
    <label>Jenis riwayat<select value={source} onChange={event=>{setSource(event.target.value);setPage(1);}}><option value="">Semua riwayat</option><option value="LOCATION">Lokasi dan observasi</option><option value="METADATA">Metadata aset</option></select></label>
    {resource.loading?<p role="status">Memuat timeline…</p>:resource.error?<ErrorNotice error={resource.error} retry={resource.reload}/>:<>
      {!(resource.data?.items??[]).length?<p>Belum ada event sesuai filter.</p>:<ol className="location-records">{resource.data!.items.map(item=><li key={`${item.source}:${item.id}`}><h3>{eventNames[item.event_type]??item.event_type}</h3><p className="catalog-hint">Kejadian {item.occurred_at} · Direkam {item.recorded_at} · Aktor {item.actor_id}</p><details><summary>Rincian bukti tersimpan</summary><pre>{JSON.stringify(item.payload_json,null,2)}</pre></details></li>)}</ol>}
      {resource.data?.items&&<Pagination page={page} totalPages={resource.data.total_pages} total={resource.data.total} onPage={setPage}/>}</>}
  </section>;
}
export default function AssetLocation({ asset, revision, editable, onChanged, onEditing }: { asset:Asset; revision:number; editable:boolean; onChanged:()=>void; onEditing:(value:boolean)=>void }) {
  const role=useCatalogRole(); const [mode,setMode]=useState(""); const [movementPage,setMovementPage]=useState(1);
  const state=useCatalogResource<LocationStatus>(`/assets/${asset.id}/location-status`,revision);
  const tree=useCatalogResource<Tree>("/locations/tree",revision);
  const movements=useCatalogResource<Page<Movement>>(`/assets/${asset.id}/movements?page_size=5&page=${movementPage}`,revision);
  const open=(value:string)=>{setMode(value);onEditing(!!value);};
  const done=()=>{open("");onChanged();};
  const refresh=()=>{state.reload();tree.reload();movements.reload();onChanged();};
  return <><section className="catalog-panel"><div className="catalog-section-heading"><h2>Lokasi resmi</h2><button type="button" className="secondary" disabled={!!mode} onClick={refresh}>Muat ulang lokasi aset</button></div>
    {state.loading||tree.loading?<p role="status">Memuat lokasi resmi…</p>:state.error||tree.error?<ErrorNotice error={(state.error||tree.error)!} retry={refresh}/>:state.data&&<>
      <p className="location-official">{locationName(state.data.current_location_id,tree.data?.items??[])}</p><p>Terakhir diverifikasi: {state.data.location_verified_at??"Belum diverifikasi"}</p>
      <p className={state.data.location_conflict?"catalog-error":"catalog-notice"} role="status">{statusNames[state.data.status]??"Status lokasi belum tersedia"}</p>
      <p className="catalog-hint">Lokasi resmi terakhir bukan jaminan posisi fisik saat ini atau bukti tunggal identitas.</p>
      {!mode&&editable&&<div className="catalog-actions">{!state.data.current_location_id&&role==="ADMIN"&&asset.lifecycle_status!=="ARCHIVED"&&<button onClick={()=>open("initial")}>Tetapkan lokasi awal</button>}{!!state.data.current_location_id&&canObserve(role)&&asset.lifecycle_status!=="ARCHIVED"&&<button onClick={()=>open("move")}>Ajukan perpindahan</button>}{canObserve(role)&&<button className="secondary" onClick={()=>open("observe")}>Catat observasi</button>}</div>}
      {mode&&<EvidenceForm key={mode} asset={asset} status={state.data} locations={tree.data?.items??[]} mode={mode} onDone={done}/>}
    </>}
  </section>
  <section className="catalog-panel"><h2>Request perpindahan aset</h2>{movements.loading?<p role="status">Memuat request…</p>:movements.error?<ErrorNotice error={movements.error} retry={movements.reload}/>:movements.data?.items&&<><MovementList items={movements.data.items} locations={tree.data?.items??[]} onChanged={onChanged} writable={editable&&!mode&&!tree.loading&&!tree.error}/><Pagination page={movementPage} totalPages={movements.data.total_pages} total={movements.data.total} onPage={setMovementPage}/></>}</section>
  <ObservationHistory id={asset.id} revision={revision} onChanged={onChanged}/><Timeline id={asset.id} revision={revision}/></>;
}
