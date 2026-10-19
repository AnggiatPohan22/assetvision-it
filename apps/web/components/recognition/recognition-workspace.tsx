"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useCatalogRole, ErrorNotice, Pagination } from "../catalog/shared";
import { catalogRequest, validatePhoto, type Page, type DeviceModel } from "../../lib/catalog";
import { locationPath, type Tree, type Location } from "../../lib/locations";
import { recognitionMutation, getSurveys, uploadRecognition, statusLabel, type Job, type Visual, type OCR, type Survey, type Summary } from "../../lib/recognition";
import SurveyDetail from "./survey-detail";

export default function RecognitionWorkspace() {
 const role = useCatalogRole(); const writable = role !== "VIEWER";
 const [locations,setLocations] = useState<Location[]>([]);
 const [models,setModels] = useState<Record<string,string>>({});
 const [pending,setPending] = useState<Job[]>([]);
 const [items,setItems] = useState<Summary[]>([]); const [page,setPage] = useState(1);
 const [paging,setPaging] = useState({total:0,total_pages:0});
 const [photo,setPhoto] = useState<File|null>(null); const [label,setLabel] = useState<File|null>(null);
 const [modelJob,setModelJob] = useState<Job|null>(null); const [labelJob,setLabelJob] = useState<Job|null>(null);
 const [correction,setCorrection] = useState(""); const [location,setLocation] = useState("");
 const [notes,setNotes] = useState(""); const [unknown,setUnknown] = useState(false);
 const [selected,setSelected] = useState<Survey|null>(null);
 const [busy,setBusy] = useState(false); const [blocked,setBlocked] = useState(false);
 const [error,setError] = useState<Error|null>(null); const [loading,setLoading] = useState(true);
 const guard = useRef(false); const requestId = useRef<string|null>(null);
 async function loadList(current: number) {
   const result = await getSurveys(current); setItems(result.items); setPaging(result);
 }
 useEffect(()=>{let active=true;
   Promise.all([catalogRequest<Tree>("/locations/tree"),getSurveys(page),catalogRequest<Page<DeviceModel>>("/device-models?page_size=100"),catalogRequest<{items:Job[]}>("/recognition/jobs")]).then(([tree,list,catalog,uploads])=>{
     if(!active)return; setLocations(tree.items);setItems(list.items);setPaging(list);setPending(uploads.items);
     setModels(Object.fromEntries(catalog.items.map(m=>[m.id,m.model_name])));
   }).catch(e=>{if(active)setError(e);}).finally(()=>{if(active)setLoading(false);});
   return ()=>{active=false;};
 },[page]);
 async function analyze(e: FormEvent) {
   e.preventDefault(); if(guard.current||blocked||!photo)return;
   try { validatePhoto(photo); if(label)validatePhoto(label); }
   catch(e){setError(e as Error);return;}
   guard.current=true;setBusy(true);setError(null);
   try { const device=await uploadRecognition(photo);setModelJob(device);
     const text=label?await uploadRecognition(label,true):null;setLabelJob(text);
   } catch(e){setError(e as Error);setBlocked(true);} finally{guard.current=false;setBusy(false);}
 }
 async function save(e: FormEvent) {
   e.preventDefault();if(guard.current||blocked||!modelJob)return;
   guard.current=true;setBusy(true);setError(null);
   requestId.current ??= crypto.randomUUID();
   try { const result = await recognitionMutation<Survey>("/recognition/observations",{
     request_id:requestId.current,device_job_id:modelJob.id,label_job_id:labelJob?.id??null,
     observed_location_id:location||null,correction:correction?{corrected_text:correction}:null,
     notes,force_unknown:unknown,
   });setSelected(result);setModelJob(null);setLabelJob(null);requestId.current=null;
     setPhoto(null);setLabel(null);setCorrection("");setNotes("");setUnknown(false);await loadList(page).catch(setError);
   }catch(e){setError(e as Error);setBlocked(true);}finally{guard.current=false;setBusy(false);}
 }
 async function open(id:string){setError(null);try{setSelected(await catalogRequest<Survey>(`/recognition/observations/${id}`));}catch(e){setError(e as Error);}}
 const visual = modelJob?.result as Visual|undefined;
 const ocr = labelJob?.result as OCR|undefined;
 return <><p className="eyebrow">SURVEI / BUKTI PERANGKAT</p><h1>Observasi perangkat</h1>
 <p>Foto membantu mencari kandidat model. Identitas unit harus ditinjau melalui bukti SN/MAC. Lokasi tidak berubah melalui observasi ini.</p>
 {error&&<ErrorNotice error={error}/>}
 {blocked&&<p role="alert">Hasil penyimpanan belum pasti. Isian dipertahankan dan pengiriman diblokir. Periksa daftar observasi sebelum memulai ulang. <button type="button" onClick={()=>window.location.reload()}>Muat ulang dan periksa riwayat</button></p>}
 {loading?<p role="status">Memuat observasi…</p>:<>
 {writable&&!modelJob&&pending.some(j=>j.kind==="MODEL")&&<section className="catalog-panel"><h2>Foto tersimpan yang belum dipakai</h2><p>Gunakan foto sebelumnya bila unggahan terputus setelah tersimpan.</p><ul>{pending.filter(j=>j.kind==="MODEL").map(j=><li key={j.id}><button type="button" onClick={()=>{setModelJob(j);setLabelJob(null);}}>Gunakan foto {j.id.slice(0,8)}</button></li>)}</ul></section>}
 {writable&&!modelJob&&<form onSubmit={analyze} className="catalog-panel"><h2>Foto perangkat</h2><fieldset disabled={busy||blocked}>
 <label>Foto perangkat (wajib)<input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" required onChange={e=>setPhoto(e.target.files?.[0]??null)}/></label>
 <label>Foto label (opsional)<input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={e=>setLabel(e.target.files?.[0]??null)}/></label>
 <p>JPEG, PNG atau WebP, maksimal 8 MiB dan sisi 4096 piksel. Foto tersimpan privat di workspace.</p>
 <button disabled={!photo} type="submit">{busy?"Memproses foto…":"Analisis foto"}</button></fieldset></form>}
 {modelJob&&<section className="catalog-panel"><h2>Hasil awal</h2>
 <button type="button" className="secondary" disabled={busy||blocked} onClick={()=>{
   setPending(current=>[modelJob,...(labelJob?[labelJob]:[]),...current.filter(j=>j.id!==modelJob.id&&j.id!==labelJob?.id)]);
   setModelJob(null);setLabelJob(null);setCorrection("");setUnknown(false);
 }}>Pilih foto lain dan kosongkan koreksi label</button>
 <img src={modelJob.content_url} alt="Foto perangkat untuk observasi" style={{maxWidth:"100%",maxHeight:280}}/>
 <p>{statusLabel[visual?.status??""]??"Belum dikenali"}. Kandidat bukan kepastian identitas.</p>
 {!visual?.candidates.length&&<p>Analisis visual belum tersedia atau belum memiliki referensi yang layak. Anda tetap dapat mencatat perangkat yang belum dikenali dan mengisi label manual.</p>}
 <ol>{visual?.candidates.map(c=><li key={c.device_model_id}>{models[c.device_model_id]??c.device_model_id} · similarity {c.similarity.toFixed(4)}</li>)}</ol>
 {visual?.encoder&&<p>Versi analisis: {visual.encoder.name} / {visual.encoder.version}</p>}
 {labelJob&&<><h3>Teks label asli</h3><pre>{ocr?.raw_text||"Label belum terbaca. Isi koreksi manual bila tersedia."}</pre></>}
 <form onSubmit={save}><fieldset disabled={busy||blocked}>
 {pending.some(j=>j.kind==="OCR")&&<label>Foto label tersimpan<select value={labelJob?.id??""} onChange={e=>setLabelJob(pending.find(j=>j.id===e.target.value)??null)}><option value="">Tanpa foto label tersimpan</option>{pending.filter(j=>j.kind==="OCR").map(j=><option key={j.id} value={j.id}>Label {j.id.slice(0,8)}</option>)}</select></label>}
 <label>Lokasi pengamatan<select value={location} onChange={e=>setLocation(e.target.value)}><option value="">Lokasi belum diketahui</option>{locations.filter(l=>l.is_active).map(l=><option key={l.id} value={l.id}>{locationPath(l,locations)} ({l.code})</option>)}</select></label>
 <label>Koreksi label manual<textarea value={correction} maxLength={16384} onChange={e=>setCorrection(e.target.value)} placeholder={"SN: ABC123\nLAN MAC: 00:11:22:33:44:55"}/></label>
 <p>Pertahankan karakter yang terlihat; jangan menebak SN rusak. Tulis LAN MAC atau WLAN MAC bila tipe diketahui. Teks asli tidak diganti oleh koreksi.</p>
 <label>Catatan observasi<textarea required maxLength={2000} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
 <label className="catalog-check"><input type="checkbox" checked={unknown} onChange={e=>setUnknown(e.target.checked)}/>Tidak dikenali / perangkat baru — simpan tanpa kandidat unit</label>
 <button type="submit">{busy?"Menyimpan…":"Simpan observasi"}</button>
 </fieldset></form></section>}
 {selected&&<SurveyDetail observation={selected} onReviewed={record=>{setSelected(record);void loadList(page).catch(setError);}}/>}
 <section className="catalog-panel"><h2>Riwayat observasi</h2>{!items.length&&<p>Belum ada observasi.</p>}
 <ul>{items.map(item=><li key={item.id}><button type="button" onClick={()=>open(item.id)}>{item.notes}</button> · {item.location_name??"Lokasi belum diketahui"} · {statusLabel[item.result_status]??item.result_status} · {statusLabel[item.review_status]??item.review_status}</li>)}</ul>
 <Pagination page={page} totalPages={paging.total_pages} total={paging.total} onPage={setPage}/></section>
 </>}
 </>;
}
