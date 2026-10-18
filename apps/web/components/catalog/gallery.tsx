"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { catalogMutation, validatePhoto, type DeviceModel, type ImageList, type ImageUpload, type ReferenceImage } from "../../lib/catalog";
import { useCatalogResource } from "./resource";
import { ConfirmButton, Empty, ErrorNotice, Loading } from "./shared";

function ReferencePhoto({ image, name }: { image: ReferenceImage; name: string }) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  return failed ? <div className="catalog-photo-failed"><p>Foto belum dapat dimuat. Periksa sesi atau coba lagi.</p><button type="button" className="secondary" onClick={() => { setFailed(false); setAttempt(value => value + 1); }}>Muat ulang foto</button></div>
    : <a href={image.content_url} target="_blank" rel="noreferrer" aria-label={`Buka foto ${image.angle ?? name} ukuran penuh`}><img key={attempt} src={image.content_url} alt={`${name} — ${image.angle ?? "foto referensi"}`} width={400} height={300} loading="lazy" onError={() => setFailed(true)} /></a>;
}

export default function Gallery({ model, editable, onChanged, onBusy }: { model: DeviceModel; editable: boolean; onChanged: () => void; onBusy: (busy: boolean) => void }) {
  const path = `/device-models/${model.id}/reference-images`;
  const resource = useCatalogResource<ImageList>(path, model.version);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const [message, setMessage] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !resource.data || !editable || !model.is_active) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const input = form.elements.namedItem("photos") as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    let completed = 0;
    let changed = false;
    let controller: AbortController | undefined;
    setError(undefined); setMessage("");
    try {
      if (!files.length) throw new Error("Pilih minimal satu foto.");
      files.forEach(validatePhoto);
      setBusy(true); onBusy(true);
      controller = new AbortController(); request.current = controller;
      let version = resource.data.model_version;
      for (const file of files) {
        const body = new FormData();
        body.set("file", file); body.set("version", String(version));
        const angle = String(values.get("angle") ?? "").trim();
        if (angle) body.set("angle", angle);
        const result = await catalogMutation<ImageUpload>(path, "POST", body, controller.signal);
        version = result.model_version; completed++; changed = true;
      }
      setMessage(`${completed} foto berhasil diunggah.`);
    } catch (cause) {
      if (!controller?.signal.aborted) {
        setError(cause instanceof Error ? cause : new Error("Foto belum dapat diunggah."));
        if (completed) setMessage(`${completed} foto sudah berhasil diunggah. Foto berikutnya belum berhasil; periksa galeri sebelum mencoba lagi.`);
      }
    } finally {
      if (controller) form.reset();
      setBusy(false); onBusy(false);
      // A failed connection may follow a successful commit: refresh, never auto-retry POST.
      if (controller) resource.reload();
      if (changed || controller) onChanged();
      request.current = null;
    }
  }
  async function remove(image: ReferenceImage) {
    if (busy || !resource.data || !editable) return;
    setBusy(true); onBusy(true); setError(undefined); setMessage("");
    request.current = new AbortController();
    try {
      await catalogMutation(`${path}/${image.id}?version=${resource.data.model_version}`, "DELETE", undefined, request.current.signal);
      setMessage("Foto telah dihapus dari katalog.");
    } catch (cause) { if (!request.current.signal.aborted) setError(cause instanceof Error ? cause : new Error("Foto belum dapat dihapus.")); }
    finally { setBusy(false); onBusy(false); resource.reload(); onChanged(); }
  }
  return <section className="catalog-gallery" aria-labelledby="gallery-heading"><div className="catalog-section-heading"><div><h2 id="gallery-heading">Foto referensi</h2><p className="catalog-hint">Foto membantu mengenali model; bukan bukti identitas unik unit fisik.</p></div></div>
    {message && <p className="catalog-success" role="status">{message}</p>}{error && <ErrorNotice error={error} />}
    {resource.loading ? <Loading /> : resource.error ? <ErrorNotice error={resource.error} retry={resource.reload} /> : resource.data && <>
      {resource.data.items.length ? <div className="catalog-photo-grid">{resource.data.items.map(image => <figure className="catalog-photo" key={image.id}><ReferencePhoto image={image} name={model.model_name} /><figcaption><div><strong>{image.angle ?? "Foto referensi"}</strong><span className="catalog-hint">{image.is_primary ? "Foto utama · " : ""}{Math.ceil(image.byte_size / 1024)} KB</span></div>
        {editable && <ConfirmButton label="Hapus foto" title="Hapus foto referensi?" disabled={busy} onConfirm={() => void remove(image)}>Foto ini akan dihapus. Model perangkat tetap tersimpan.</ConfirmButton>}</figcaption></figure>)}</div>
        : <Empty><p>Belum ada foto referensi untuk model ini.</p></Empty>}
      {editable && model.is_active && <form className="catalog-panel catalog-upload" onSubmit={upload} aria-label="Unggah foto referensi"><fieldset disabled={busy}><legend>Tambah foto referensi</legend><p className="catalog-hint">JPEG, PNG, atau WebP; maksimal 8 MiB per foto. Batas workspace dapat lebih kecil. Foto diproses satu per satu.</p><label>Pilih foto<input type="file" name="photos" multiple required accept="image/jpeg,image/png,image/webp" /></label><label>Sudut / keterangan singkat (opsional)<input name="angle" maxLength={100} placeholder="Misalnya: tampak depan" /></label><button type="submit">{busy ? "Mengunggah…" : "Unggah foto"}</button></fieldset></form>}
      {editable && !model.is_active && <p className="catalog-notice">Pulihkan model sebelum menambahkan foto baru.</p>}
    </>}
  </section>;
}
