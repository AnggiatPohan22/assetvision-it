"use client";
export default function ErrorPage({reset}:{reset:()=>void}) { return <section role="alert"><h1>Observasi belum tersedia</h1><button onClick={reset}>Muat ulang</button></section>; }
