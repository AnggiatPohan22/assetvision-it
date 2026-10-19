import { getCurrentUser } from "../../lib/auth";
import MovementInbox from "../../components/locations/movements";
export default async function MovementsPage() {
  const { user } = await getCurrentUser();
  if (user?.role !== "ADMIN") return <section className="catalog-panel"><h1>Akses terbatas</h1><p>Inbox perpindahan hanya untuk administrator. Buka detail aset untuk melihat request Anda.</p><a href="/assets">Daftar aset</a></section>;
  return <MovementInbox/>;
}
