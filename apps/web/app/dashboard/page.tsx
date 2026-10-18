import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import LogoutButton from "./logout-button";
export const dynamic = "force-dynamic";
export default async function Dashboard() {
  const { user, unavailable } = await getCurrentUser();
  if (unavailable) return <main className="status-page"><h1>Layanan belum tersedia</h1>
    <p>Workspace belum dapat terhubung ke API. Silakan muat ulang halaman.</p></main>;
  if (!user) redirect("/login");
  return <main className="dashboard">
    <header><Link className="brand dark" href="/dashboard">AV<span>AssetVision IT</span></Link>
      <div className="account"><span className="role">{user.role}</span><LogoutButton /></div></header>
    <section className="dashboard-content">
      <p className="eyebrow">WORKSPACE / OVERVIEW</p><h1>Selamat datang, {user.name}.</h1>
      <p className="muted">Akses Anda aktif sebagai {user.role}. Fondasi workspace siap digunakan.</p>
      <div className="summary-grid">
        <article><span className="card-number">01</span><h2>Akses terverifikasi</h2>
          <p>Identitas dan izin akun diperiksa oleh server.</p></article>
        <article><span className="card-number">02</span><h2>Data tetap lokal</h2>
          <p>PostgreSQL menjadi sumber data utama workspace.</p></article>
        <article><span className="card-number">03</span><h2>Fondasi audit</h2>
          <p>Aktivitas autentikasi memiliki jejak audit.</p></article>
      </div>
      <aside className="notice"><span className="role">KATALOG</span>
        <div><h2>Kenali model perangkat Anda</h2>
          <p>Telusuri model, spesifikasi, dan foto referensi. <Link href="/catalog/models" style={{ textDecoration: "underline" }}>Buka katalog perangkat →</Link></p></div></aside>
    </section>
  </main>;
}
