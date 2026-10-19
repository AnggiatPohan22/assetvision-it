"use client";
import { useRef, useState, type FormEvent } from "react";
import { ErrorNotice, useCatalogRole } from "../catalog/shared";
import { identifierName, recognitionMutation, evidenceReason, statusLabel, type Survey } from "../../lib/recognition";

export default function SurveyDetail({observation: record,onReviewed}:{observation:Survey;onReviewed:(record:Survey)=>void}) {
 return <section className="catalog-panel"><h2>Detail observasi</h2><p>{record.notes}</p>
 <p>{record.created_by} · {record.observed_at} · {record.evidence.location_name??"Lokasi belum diketahui"}</p>
 <img src={`/api/v1/recognition/jobs/${record.device_job_id}/content`} alt="Bukti foto perangkat tersimpan" style={{maxWidth:"100%",maxHeight:280}}/>
 <h3>Prediksi awal — tetap disimpan</h3><p>{statusLabel[record.evidence.fusion.status]??record.evidence.fusion.status}</p>
 <p>Model: {statusLabel[record.evidence.visual.status]??record.evidence.visual.status}</p>
 <ol>{record.evidence.visual.candidates.map(c=><li key={c.device_model_id}>{record.evidence.model_names[c.device_model_id]??c.device_model_id} · similarity {c.similarity.toFixed(4)}</li>)}</ol>
 <ul>{record.evidence.fusion.candidates.map(c=><li key={c.asset_id}>{record.evidence.asset_codes[c.asset_id]??c.asset_id} · {c.reasons.map(evidenceReason).join(" · ")}</li>)}</ul>
 {record.evidence.fusion.status==="CONFLICT"&&<p role="alert">Bukti bertentangan. Periksa label dan riwayat. Perpindahan lokasi harus melalui workflow perpindahan.</p>}
 <details><summary>Alasan keputusan awal</summary><ul>{record.evidence.fusion.reasons.map(r=><li key={r}>{evidenceReason(r)}</li>)}</ul></details>
 {record.label_job_id&&<>
 <img src={`/api/v1/recognition/jobs/${record.label_job_id}/content`} alt="Bukti foto label tersimpan" style={{maxWidth:"100%",maxHeight:220}}/></>}
 <h3>Label asli dan koreksi terpisah</h3><p>OCR asli</p><pre>{record.evidence.ocr?.raw_text||"Tidak ada teks OCR"}</pre><p>Koreksi manual</p><pre>{record.evidence.ocr?.corrected_text||"Tidak ada koreksi"}</pre>
 {record.review?<><h3>Keputusan review</h3><p>{statusLabel[record.review.evidence.result_status]??record.review.decision} · {record.review.reviewer_id} · {record.review.reviewed_at}</p><p>{record.review.notes}</p>{record.asset_id&&<a href={`/assets/${record.asset_id}`}>Buka unit yang diverifikasi</a>}</>:<ReviewForm key={record.id} record={record} onReviewed={onReviewed}/>}
 </section>;
}
function ReviewForm({record,onReviewed}:{record:Survey;onReviewed:(record:Survey)=>void}) {
 const role=useCatalogRole();const [decision,setDecision]=useState("MORE_PHOTOS");
 const [asset,setAsset]=useState("");const [checked,setChecked]=useState<number[]>([]);
 const [confirmed,setConfirmed]=useState(false);const [notes,setNotes]=useState("");
 const [busy,setBusy]=useState(false);const [blocked,setBlocked]=useState(false);const [error,setError]=useState<Error|null>(null);const guard=useRef(false);
 if(role!=="ADMIN")return <p>Menunggu review ADMIN. Observasi tidak mengubah data master.</p>;
 async function submit(e:FormEvent){e.preventDefault();if(guard.current||blocked)return;guard.current=true;setBusy(true);setError(null);
   const unit=record.evidence.unit_snapshots.find(u=>u.asset_id===asset);
   try { const reviewed=await recognitionMutation<Survey>(`/recognition/observations/${record.id}/review`,{
     version:record.version,decision,notes,...(decision==="MATCH"?{selected_asset_id:asset,asset_version:unit?.asset_version,manufacturer_id:unit?.manufacturer_id,checked_manual_indices:checked,label_checked:confirmed}:{})
   });onReviewed(reviewed);}catch(e){setError(e as Error);setBlocked(true);}finally{guard.current=false;setBusy(false);}
 }
 return <form onSubmit={submit}><h3>Review ADMIN</h3><p>Persetujuan membutuhkan identifier unik yang diperiksa pada label dan klaim master VERIFIED. Model dan lokasi saja tidak cukup. Data master tidak diubah.</p>
 {error&&<ErrorNotice error={error}/>}{blocked&&<p role="alert">Review belum dapat dipastikan atau bukti berubah. Draft tetap ada; periksa riwayat dan muat ulang sebelum melanjutkan.</p>}
 <fieldset disabled={busy||blocked}><label>Keputusan<select value={decision} onChange={e=>setDecision(e.target.value)}><option value="MORE_PHOTOS">Minta foto tambahan</option><option value="UNKNOWN">Tidak dikenali</option><option value="CONFLICT">Konflik bukti</option><option value="MATCH" disabled={record.evidence.force_unknown}>Verifikasi unit dari identifier</option></select></label>
 {decision==="MATCH"&&<><label>Unit yang diperiksa<select required value={asset} onChange={e=>setAsset(e.target.value)}><option value="">Pilih unit</option>{record.evidence.unit_snapshots.map(u=><option key={u.asset_id} value={u.asset_id} disabled={u.archived}>{record.evidence.asset_codes[u.asset_id]??u.asset_id}</option>)}</select></label>
 {asset&&<div><a href={`/assets/${asset}`} target="_blank" rel="noopener noreferrer">Periksa master dan riwayat unit</a><ul>{record.evidence.unit_snapshots.find(u=>u.asset_id===asset)?.claims.map((c,i)=><li key={i}>{identifierName(c.kind)}: {c.value} · {c.verification==="VERIFIED"?"Sudah diverifikasi":c.verification==="DISPUTED"?"Diperselisihkan":"Belum diverifikasi"}</li>)}</ul></div>}
 <p>Pilih identifier yang sudah diperiksa dari koreksi manual:</p>{record.evidence.ocr?.manual_candidates.map((c,i)=><label key={i} className="catalog-check"><input type="checkbox" checked={checked.includes(i)} onChange={e=>setChecked(e.target.checked?[...checked,i]:checked.filter(n=>n!==i))}/>{identifierName(c.kind)}: {c.normalized_value}</label>)}
 <label className="catalog-check"><input type="checkbox" required checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>Saya sudah memeriksa label fisik/sumber dan tipe identifier, bukan hanya foto model atau lokasi.</label></>}
 <label>Alasan review<textarea required maxLength={2000} value={notes} onChange={e=>setNotes(e.target.value)}/></label><button type="submit" disabled={decision==="MATCH"&&(!asset||!checked.length||!confirmed)}>{busy?"Menyimpan review…":"Simpan keputusan review"}</button></fieldset></form>;
}
