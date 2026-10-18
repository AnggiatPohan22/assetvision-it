"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <section className="catalog-panel" role="alert"><h1>Halaman belum dapat dimuat</h1><p>Periksa hasil perubahan sebelum mengirim ulang. Jika commit impor terputus, gunakan permintaan dan kunci impor yang sama.</p><button onClick={reset}>Coba muat lagi</button></section>; }
