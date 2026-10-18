"use client";
import type { ScalarDraft, SpecDraft } from "../../lib/catalog-form";

const names = { text: "Teks", number: "Angka", boolean: "Ya / tidak", empty: "Kosong", list: "Daftar" };
function ScalarInput({ value, onChange, label }: { value: ScalarDraft; onChange: (value: ScalarDraft) => void; label: string }) {
  return <div className="catalog-scalar"><label><span className="sr-only">Jenis {label}</span><select value={value.kind} onChange={event => onChange({ kind: event.target.value as ScalarDraft["kind"], value: "" })}>
    {Object.entries(names).filter(([key]) => key !== "list").map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
    {value.kind === "boolean" ? <label><span className="sr-only">{label}</span><select value={value.value || "false"} onChange={event => onChange({ ...value, value: event.target.value })}><option value="false">Tidak</option><option value="true">Ya</option></select></label>
      : value.kind !== "empty" && <label><span className="sr-only">{label}</span><input value={value.value} maxLength={500} inputMode={value.kind === "number" ? "decimal" : "text"} onChange={event => onChange({ ...value, value: event.target.value })} /></label>}
  </div>;
}
export default function SpecEditor({ rows, onChange }: { rows: SpecDraft[]; onChange: (rows: SpecDraft[]) => void }) {
  const update = (index: number, row: SpecDraft) => onChange(rows.map((value, i) => i === index ? row : value));
  return <section className="catalog-spec-editor"><div className="catalog-section-heading"><div><h3>Spesifikasi</h3><p className="catalog-hint">Opsional. Maksimal 32 spesifikasi; gunakan nama seperti jumlah_port atau daya_watt.</p></div>
    <button className="secondary" type="button" disabled={rows.length >= 32} onClick={() => onChange([...rows, { key: "", kind: "text", value: "", items: [] }])}>Tambah spesifikasi</button></div>
    {rows.map((row, index) => <div className="catalog-spec-row" key={index}><div className="catalog-spec-main">
      <label>Nama spesifikasi {index + 1}<input value={row.key} maxLength={64} onChange={event => update(index, { ...row, key: event.target.value })} /></label>
      <label>Jenis nilai<select value={row.kind} onChange={event => update(index, { ...row, kind: event.target.value as SpecDraft["kind"], value: "", items: [] })}>{Object.entries(names).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
      <button type="button" className="secondary" aria-label={`Hapus spesifikasi ${index + 1}`} onClick={() => onChange(rows.filter((_, i) => i !== index))}>Hapus</button></div>
      {row.kind === "list" ? <div className="catalog-spec-list">{row.items.map((item, itemIndex) => <div className="catalog-actions" key={itemIndex}><ScalarInput value={item} label={`Nilai ${itemIndex + 1} spesifikasi ${index + 1}`} onChange={value => update(index, { ...row, items: row.items.map((old, i) => i === itemIndex ? value : old) })} /><button type="button" className="secondary" aria-label={`Hapus nilai ${itemIndex + 1} spesifikasi ${index + 1}`} onClick={() => update(index, { ...row, items: row.items.filter((_, i) => i !== itemIndex) })}>Hapus nilai</button></div>)}
        <button type="button" className="secondary" disabled={row.items.length >= 20} onClick={() => update(index, { ...row, items: [...row.items, { kind: "text", value: "" }] })}>Tambah nilai</button></div>
        : <ScalarInput value={row as ScalarDraft} label={`Nilai spesifikasi ${index + 1}`} onChange={value => update(index, { ...row, ...value })} />}
    </div>)}
  </section>;
}
