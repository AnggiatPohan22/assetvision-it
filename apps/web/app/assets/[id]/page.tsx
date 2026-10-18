import { notFound } from "next/navigation";
import AssetDetail from "../../../components/assets/asset-detail";
export default async function AssetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) notFound();
  return <AssetDetail id={id} />;
}
