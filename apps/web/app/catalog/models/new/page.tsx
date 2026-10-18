import { getCurrentUser } from "../../../../lib/auth";
import NewModel from "../../../../components/catalog/new-model";
export default async function NewModelPage() {
  const { user } = await getCurrentUser();
  if (user?.role !== "ADMIN") return <section className="catalog-panel"><h1>Akses terbatas</h1><p>Hanya administrator yang dapat menambahkan model.</p><a href="/catalog/models">Kembali ke katalog</a></section>;
  return <NewModel />;
}
