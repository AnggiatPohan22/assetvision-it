import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "../../lib/auth";
import { CatalogProvider } from "../../components/catalog/shared";
import LogoutButton from "../dashboard/logout-button";
import "./catalog.css";

export const dynamic = "force-dynamic";
export default async function CatalogLayout({ children }: { children: React.ReactNode }) {
  const { user, unavailable } = await getCurrentUser();
  if (unavailable) return <main className="status-page"><h1>Layanan belum tersedia</h1><p>Katalog belum dapat terhubung. <a href="/catalog/models">Muat ulang halaman</a>.</p></main>;
  if (!user) redirect("/login");
  return <CatalogProvider role={user.role}><div className="catalog-shell"><a className="catalog-skip" href="#catalog-main">Lewati ke isi katalog</a>
    <header className="catalog-header"><Link className="brand" href="/dashboard">AV<span>AssetVision IT</span></Link><div className="catalog-account"><span>{user.name}</span><span className="role">{user.role}</span><LogoutButton /></div></header>
    <nav className="catalog-nav" aria-label="Navigasi workspace"><Link href="/dashboard">Workspace</Link><Link href="/catalog/models">Model perangkat</Link><Link href="/assets">Aset fisik</Link><Link href="/locations">Lokasi</Link><Link href="/recognition">Observasi perangkat</Link>{user.role === "ADMIN" && <Link href="/movements">Inbox perpindahan</Link>}{user.role === "ADMIN" && <Link href="/catalog/settings">Kategori & produsen</Link>}<span>Katalog lokal</span></nav>
    <main id="catalog-main" className="catalog-content">{children}</main><footer className="catalog-footer">AssetVision IT · Katalog model perangkat · Data tetap lokal</footer>
  </div></CatalogProvider>;
}
