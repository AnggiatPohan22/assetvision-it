"use client";
import { useState } from "react";
import { descendants, kinds, locationPath, treeRows, type Location, type Tree } from "../../lib/locations";
import { useCatalogResource } from "../catalog/resource";
import { ErrorNotice, Status, useCatalogRole } from "../catalog/shared";
import { WriteForm } from "./shared";

function LocationForm({ initial, items, onSaved, onCancel }: { initial?:Location; items:Location[]; onSaved:()=>void; onCancel:()=>void }) {
  const [snapshot]=useState(initial);
  const [code,setCode]=useState(initial?.code??""); const [name,setName]=useState(initial?.name??"");
  const [kind,setKind]=useState<Location["kind"]>(initial?.kind??"SITE"); const [parent,setParent]=useState(initial?.parent_id??"");
  const [active,setActive]=useState(initial?.is_active??true);
  const index=new Map(items.map(item=>[item.id,item]));
  const excluded=snapshot?descendants(snapshot.id,items):new Set<string>();
  return <WriteForm title={snapshot?"Edit lokasi":"Lokasi baru"} submitLabel="Simpan lokasi" onSaved={onSaved} onCancel={onCancel} prepare={()=>{
    if(!/^[a-z0-9][a-z0-9_-]{0,49}$/.test(code.trim().toLowerCase())) throw new Error("Kode wajib 1–50 huruf/angka, garis bawah atau tanda hubung.");
    if(!name.trim()||name.trim().length>200) throw new Error("Nama wajib diisi, maksimal 200 karakter.");
    return {path:snapshot?`/locations/${snapshot.id}`:"/locations",method:snapshot?"PATCH":"POST",body:{code:code.trim().toLowerCase(),name:name.trim(),kind,parent_id:parent||null,is_active:active,...(snapshot?{version:snapshot.version}:{})}};
  }}><div className="catalog-form-grid"><label>Kode lokasi<input required maxLength={50} value={code} onChange={event=>setCode(event.target.value)}/></label><label>Nama lokasi<input required maxLength={200} value={name} onChange={event=>setName(event.target.value)}/></label>
    <label>Jenis lokasi<select value={kind} onChange={event=>setKind(event.target.value as Location["kind"])}>{Object.entries(kinds).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
    <label>Induk lokasi<select value={parent} onChange={event=>setParent(event.target.value)}><option value="">Tanpa induk (root)</option>{items.filter(item=>!excluded.has(item.id)).map(item=><option key={item.id} value={item.id}>{locationPath(item,items,index)}{item.is_active?"":" · diarsipkan"}</option>)}</select></label></div>
    <label className="catalog-check"><input type="checkbox" checked={active} onChange={event=>setActive(event.target.checked)}/>Lokasi aktif</label>
    <p className="catalog-hint">Mengarsipkan lokasi tidak menghapus riwayat, memindahkan aset, atau otomatis mengarsipkan anak. Koordinat GPS existing dipertahankan.</p>
  </WriteForm>;
}
export default function LocationManager() {
  const role=useCatalogRole(); const [revision,setRevision]=useState(0);
  const resource=useCatalogResource<Tree>("/locations/tree",revision);
  const [editor,setEditor]=useState<Location|"new">(); const [search,setSearch]=useState(""); const [notice,setNotice]=useState("");
  const refresh=()=>{setEditor(undefined);setRevision(value=>value+1);};
  const items=resource.data?.items??[];
  const index=new Map(items.map(item=>[item.id,item]));
  return <><div className="catalog-title"><div><p className="eyebrow">LOKASI / HIERARKI</p><h1>Lokasi aset</h1><p className="muted">Site, area, bangunan, lantai, ruangan dan titik penempatan.</p></div>{role==="ADMIN"&&<button disabled={resource.loading||!!resource.error||!!editor} onClick={()=>setEditor("new")}>Tambah lokasi</button>}</div>
    {notice&&<p className="catalog-success" role="status">{notice}</p>}
    {resource.loading?<p role="status">Memuat hierarki lokasi…</p>:resource.error?<ErrorNotice error={resource.error} retry={resource.reload}/>:<>
      {editor&&role==="ADMIN"&&<LocationForm key={editor==="new"?"new":editor.id} initial={editor==="new"?undefined:editor} items={items} onSaved={()=>{setNotice("Lokasi tersimpan; riwayat aset tetap dipertahankan.");refresh();}} onCancel={refresh}/>}
      <section className="catalog-panel"><div className="catalog-section-heading"><h2>Hierarki lokasi</h2><button type="button" className="secondary" disabled={!!editor} onClick={refresh}>Muat ulang lokasi</button></div>
      <label>Cari lokasi<input type="search" value={search} onChange={event=>setSearch(event.target.value)}/></label>
      {!items.length?<p>Belum ada lokasi. Administrator dapat membuat lokasi awal.</p>:<ul className="location-tree" aria-label="Hierarki lokasi">{treeRows(items).filter(({item})=>locationPath(item,items,index).toLowerCase().includes(search.toLowerCase())||item.code.includes(search.toLowerCase())).map(({item,depth})=><li key={item.id} style={{paddingInlineStart:`${Math.min(depth,12)*12}px`}}><div className="location-row"><div><span className="catalog-hint">{locationPath(item,items,index)}</span><strong>{item.name}</strong> <span className="catalog-hint">{item.code} · {kinds[item.kind]} · Tingkat {depth+1}</span>{item.latitude!==null&&<span className="catalog-hint">Koordinat: {item.latitude}, {item.longitude}; akurasi {item.gps_accuracy_m??"belum diisi"} m · {item.gps_recorded_at??"waktu belum diisi"}</span>}</div><Status active={item.is_active}/>{role==="ADMIN"&&<button className="secondary" disabled={!!editor} aria-label={`Edit ${item.name}`} onClick={()=>setEditor(item)}>Edit / arsip</button>}</div></li>)}</ul>}
      {items.length>0&&treeRows(items).every(({item})=>!locationPath(item,items,index).toLowerCase().includes(search.toLowerCase())&&!item.code.includes(search.toLowerCase()))&&<p>Tidak ada lokasi sesuai pencarian.</p>}
      </section></>}
  </>;
}
