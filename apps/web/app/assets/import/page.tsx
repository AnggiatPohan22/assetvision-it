import { getCurrentUser } from "../../../lib/auth";
import CsvImport from "../../../components/assets/csv-import";
export default async function ImportPage() {
  const { user } = await getCurrentUser();
  if (user?.role !== "ADMIN") return <section className="catalog-panel"><h1>Akses terbatas</h1><p>Hanya administrator yang dapat mengimpor CSV.</p><a href="/assets">Kembali ke daftar aset</a></section>;
  return <CsvImport />;
}
