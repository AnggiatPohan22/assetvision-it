"use client";
import { useRef, useState, type ReactNode } from "react";
import { errorFrom } from "../../lib/assets";
import { locationMutation, locationPath, type Location } from "../../lib/locations";
import { ErrorNotice } from "../catalog/shared";

export function LocationSelect({ items, value, onChange, label="Lokasi tujuan", exclude }: { items: Location[]; value:string; onChange:(value:string)=>void; label?:string; exclude?:string }) {
  const index=new Map(items.map(item=>[item.id,item]));
  return <label>{label}<select required value={value} onChange={event=>onChange(event.target.value)}><option value="">Pilih lokasi aktif</option>{items.filter(item=>item.is_active && item.id!==exclude).map(item=><option value={item.id} key={item.id}>{locationPath(item,items,index)} ({item.code})</option>)}</select></label>;
}
export function WriteForm({ title, submitLabel, children, prepare, onSaved, onCancel, disabled=false }: { title:string; submitLabel:string; children:ReactNode; prepare:()=>{path:string;method:"POST"|"PATCH";body:object}; onSaved:()=>void; onCancel:()=>void; disabled?:boolean }) {
  const [busy,setBusy]=useState(false); const inflight=useRef(false);
  const [blocked,setBlocked]=useState(false); const [error,setError]=useState<Error>();
  return <form className="catalog-panel location-form" aria-label={title} onSubmit={async event=>{
    event.preventDefault(); if(inflight.current||blocked||disabled) return;
    let request:ReturnType<typeof prepare>;
    try { request=prepare(); } catch(cause) { setError(errorFrom(cause)); return; }
    inflight.current=true; setBusy(true); setError(undefined);
    try { await locationMutation(request.path,request.method,request.body); onSaved(); }
    catch(cause) { setError(errorFrom(cause)); setBlocked(true); }
    finally { inflight.current=false; setBusy(false); }
  }}><h3>{title}</h3>{error&&<ErrorNotice error={error}/>}
    {blocked&&<p className="catalog-notice">Pengiriman dihentikan. Isian dipertahankan; periksa data terbaru sebelum membuat permintaan baru.</p>}
    <fieldset disabled={busy||blocked||disabled}>{children}</fieldset>
    <div className="catalog-actions"><button disabled={busy||blocked||disabled}>{busy?"Menyimpan…":submitLabel}</button><button type="button" className="secondary" disabled={busy} onClick={onCancel}>{blocked?"Batalkan dan muat ulang":"Batalkan"}</button></div>
  </form>;
}
