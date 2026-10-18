import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "../../lib/auth";
import { CatalogProvider } from "../../components/catalog/shared";
import LogoutButton from "../dashboard/logout-button";
import "../catalog/catalog.css";
import "./assets.css";
export const dynamic = "force-dynamic";
export default async function AssetsLayout({ children }: { children: React.ReactNode }) {
  const { user, unavailable } = await getCurrentUser();
  if (unavailable) return <main className="status-page"><h1>Layanan belum tersedia</h1><a href="/assets">Muat ulang daftar aset</a></main>;
  if (!user) redirect("/login");
  return <CatalogProvider role={user.role}><div className="catalog-shell"><a className="catalog-skip" href="#asset-main">Lewati ke isi aset</a><header className="catalog-header"><Link className="brand" href="/dashboard">AV<span>AssetVision IT</span></Link><div className="catalog-account"><span>{user.name}</span><span className="role">{user.role}</span><LogoutButton /></div></header><nav className="catalog-nav" aria-label="Navigasi workspace"><Link href="/dashboard">Workspace</Link><Link href="/catalog/models">Model perangkat</Link><Link href="/assets">Aset fisik</Link>{user.role === "ADMIN" && <Link href="/assets/import">Impor CSV</Link>}</nav><main id="asset-main" className="catalog-content">{children}</main><footer className="catalog-footer">AssetVision IT · Registry aset fisik · Data tetap lokal</footer></div></CatalogProvider>;
}
