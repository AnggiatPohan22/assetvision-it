"use client";
import { useState } from "react";
import { type Asset } from "../../lib/assets";
import AssetForm from "./asset-form";
export default function NewAsset() {
  const [saved, setSaved] = useState<Asset>();
  return <><a className="catalog-back" href="/assets">← Daftar aset</a><h1>Tambah aset fisik</h1>{saved ? <section className="catalog-panel" role="status"><h2>{saved.asset_code} tersimpan</h2><p>Unit telah dibuat. Tambahkan identifier di halaman detail.</p><a className="catalog-button" href={`/assets/${saved.id}`}>Buka detail aset</a></section> : <AssetForm onSaved={setSaved} />}</>;
}
