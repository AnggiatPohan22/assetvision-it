import { getCurrentUser } from "../../../lib/auth";
import NewAsset from "../../../components/assets/new-asset";
export default async function NewAssetPage() {
  const { user } = await getCurrentUser();
  if (user?.role !== "ADMIN") return <section className="catalog-panel"><h1>Akses terbatas</h1><p>Hanya administrator yang dapat menambah aset.</p><a href="/assets">Kembali ke daftar aset</a></section>;
  return <NewAsset />;
}
