"use client";
export default function CatalogError({ reset }: { reset: () => void }) {
  return <section className="catalog-panel" role="alert"><h2>Katalog belum dapat dimuat</h2><p>Coba muat ulang. Perubahan tidak akan dikirim ulang otomatis.</p><button type="button" onClick={reset}>Coba lagi</button></section>;
}
