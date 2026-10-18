"use client";
import ModelForm from "./model-form";
export default function NewModel() {
  return <><a href="/catalog/models" className="catalog-back">← Semua model</a><div className="catalog-title"><div><p className="eyebrow">KATALOG PERANGKAT</p><h1>Tambah model</h1><p className="muted">Buat satu referensi untuk setiap model perangkat.</p></div></div>
    <ModelForm onSaved={model => window.location.assign(`/catalog/models/${encodeURIComponent(model.id)}`)} />
  </>;
}
