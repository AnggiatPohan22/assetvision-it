import { getCurrentUser } from "../../../lib/auth";
import MasterManager from "../../../components/catalog/master-manager";
export default async function CatalogSettingsPage() {
  const { user } = await getCurrentUser();
  if (user?.role !== "ADMIN") return <section className="catalog-panel"><h1>Akses terbatas</h1><p>Pengaturan katalog hanya tersedia bagi administrator.</p><a href="/catalog/models">Kembali ke katalog</a></section>;
  return <MasterManager />;
}
