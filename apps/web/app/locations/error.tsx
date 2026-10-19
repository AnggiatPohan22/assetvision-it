"use client";
export default function ErrorPage({ reset }: { reset:()=>void }) { return <section className="catalog-panel"><h1>Halaman belum dapat dimuat</h1><button onClick={reset}>Coba muat lagi</button></section>; }
