"use client";
import { useRef, useState, type FormEvent } from "react";
import { assetMutation, errorFrom, readCsv, type CsvRow, type ImportPayload, type ImportResult, type Preview } from "../../lib/assets";
import { ConfirmButton, ErrorNotice } from "../catalog/shared";

function Rows({ rows }: { rows: CsvRow[] }) {
  return <div className="catalog-table-wrap"><table className="catalog-table"><caption>Hasil per baris CSV</caption><thead><tr><th>Baris</th><th>Asset ID</th><th>Validasi / hasil</th><th>Petunjuk lokasi (staging)</th></tr></thead><tbody>{rows.map(row => <tr key={row.row}><td>{row.row}</td><td>{row.asset_id ? <a className="catalog-link" href={`/assets/${row.asset_id}`}>{row.asset_code}</a> : row.asset_code || "—"}</td><td>{row.asset_id ? "Tersimpan" : row.valid ? "Valid saat pemeriksaan" : "Tidak valid"}{row.errors.map((error, index) => <p key={index}>{error}</p>)}{row.collisions.map((collision, index) => <div className="catalog-notice" key={index}>Benturan {collision.identifier_type}: {collision.normalized_value}{!!collision.csv_rows.length && <p>Baris CSV: {collision.csv_rows.join(", ")}</p>}{collision.asset_ids.map(id => <a className="catalog-link asset-collision" key={id} href={`/assets/${id}`}>Unit {id}</a>)}</div>)}</td><td>{row.location_hint || "—"}</td></tr>)}</tbody></table></div>;
}
export default function CsvImport() {
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<Preview>();
  const [result, setResult] = useState<ImportResult>();
  const [ack, setAck] = useState(false);
  const [pending, setPending] = useState<ImportPayload>();
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const selection = useRef(0);
  const [error, setError] = useState<Error>();
  async function choose(file?: File) {
    const generation = ++selection.current;
    setCsv(""); setFileName(""); setPreview(undefined); setResult(undefined); setAck(false); setError(undefined);
    if (!file) return;
    setBusy(true);
    try { const text = await readCsv(file); if (generation === selection.current) { setCsv(text); setFileName(file.name); } }
    catch (cause) { if (generation === selection.current) setError(errorFrom(cause)); }
    finally { if (generation === selection.current) setBusy(false); }
  }
  async function inspect(event: FormEvent) {
    event.preventDefault(); if (lock.current || !csv || pending) return;
    lock.current = true; setBusy(true); setError(undefined); setPreview(undefined); setResult(undefined); setAck(false);
    try { setPreview(await assetMutation<Preview>("/assets/imports/preview", "POST", { csv_text: csv })); }
    catch (cause) { setError(errorFrom(cause)); }
    finally { lock.current = false; setBusy(false); }
  }
  async function commit() {
    if (lock.current || !preview || preview.invalid_rows || (preview.has_collisions && !ack && !pending) || result?.status === "COMMITTED") return;
    lock.current = true; setBusy(true); setError(undefined);
    // A retry always uses this immutable request, even after an uncertain network result.
    const payload = pending ?? { csv_text: csv, idempotency_key: crypto.randomUUID(), allow_identifier_collisions: ack };
    setPending(payload);
    try {
      const response = await assetMutation<ImportResult>("/assets/imports/commit", "POST", payload);
      setResult(response);
      if (response.status === "REJECTED") { setPending(undefined); setPreview(undefined); setAck(false); }
    } catch (cause) { setError(errorFrom(cause)); }
    finally { lock.current = false; setBusy(false); }
  }
  return <><a className="catalog-back" href="/assets">← Daftar aset</a><h1>Impor aset dari CSV</h1><p className="muted">Upload → periksa preview → konfirmasi → ringkasan. Satu batch berhasil seluruhnya atau ditolak seluruhnya.</p>
    <section className="catalog-panel"><h2>1. Pilih berkas</h2><p>UTF-8, pemisah koma, maksimal 256 KiB / 500 baris. Wajib: <code>asset_code,manufacturer,model</code>.</p><p className="catalog-hint">Opsional: serial_number, mac_address, hostname, condition, status, notes, location_hint. Nama model/produsen harus sudah ada dan aktif. SN kosong diperbolehkan. Kode existing tidak diubah. location_hint hanya staging, bukan lokasi aktif.</p><p className="catalog-hint">Status: IN_STOCK, IN_USE, MAINTENANCE, RETIRED, ARCHIVED. Kondisi: UNKNOWN, GOOD, DAMAGED, UNUSABLE. Berkas ekspor bukan template impor.</p>
      <form onSubmit={inspect} aria-label="Upload CSV"><label>Pilih CSV<input type="file" accept=".csv,text/csv" disabled={busy || !!pending} onChange={event => void choose(event.target.files?.[0])} /></label>{fileName && <p>{fileName}</p>}<button disabled={busy || !csv || !!pending} type="submit">{busy ? "Memproses…" : "Periksa preview"}</button></form>
    </section>{error && <ErrorNotice error={error} />}
    {preview && !result && <section className="catalog-panel"><h2>2. Tinjau dan konfirmasi</h2><p>{preview.total_rows} baris · {preview.valid_rows} valid · {preview.invalid_rows} invalid.</p><p>Preview belum menyimpan data dan bukan reservasi kode/model. Validasi dijalankan lagi saat commit.</p><Rows rows={preview.rows} />
      {preview.has_collisions && <label className="catalog-check"><input type="checkbox" checked={ack} disabled={busy || !!pending} onChange={event => setAck(event.target.checked)} />Saya telah meninjau benturan identifier dan mengizinkan klaim lintas unit tanpa menggabungkan data.</label>}
      {!!preview.invalid_rows && <p className="catalog-error" role="alert">Perbaiki semua baris invalid di berkas, lalu upload dan periksa ulang.</p>}
      {pending ? <div className="catalog-notice"><p>Hasil commit belum diketahui. Tetap di halaman ini dan coba ulang permintaan yang sama. Jangan mulai batch baru atau muat ulang halaman sebelum hasil dipastikan.</p><p>Kunci impor: {pending.idempotency_key}</p><button disabled={busy} onClick={() => void commit()}>Coba ulang commit yang sama</button></div> : <ConfirmButton label="Konfirmasi impor" title="Simpan batch aset ini?" disabled={busy || preview.invalid_rows > 0 || (preview.has_collisions && !ack)} onConfirm={() => void commit()}>Seluruh unit valid akan dibuat dengan Asset ID permanen. Model dan aset existing tidak ditimpa.</ConfirmButton>}
    </section>}
    {result && <section className="catalog-panel" role="status"><h2>3. {result.status === "COMMITTED" ? "Impor berhasil" : "Batch ditolak"}</h2><p>{result.created_count} dibuat · {result.failed_count} gagal. Kunci impor: {result.import_id}</p>{result.errors.map((error, index) => <p key={index}>{error}</p>)}<Rows rows={result.rows} />{result.status === "COMMITTED" ? <a className="catalog-button" href="/assets">Buka daftar aset</a> : <p>Seluruh batch dibatalkan. Perbaiki berkas atau periksa preview kembali sebelum commit baru.</p>}</section>}
  </>;
}
