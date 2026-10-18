import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import LoginForm from "./login-form";

export const dynamic = "force-dynamic";
export default async function LoginPage() {
  const { user } = await getCurrentUser();
  if (user) redirect("/dashboard");
  return <main className="login-shell">
    <section className="intro">
      <Link className="brand" href="/">AV<span>AssetVision IT</span></Link>
      <div><p className="eyebrow">INVENTARIS IT LOKAL</p>
        <h1>Fondasi yang jelas.<br />Aset yang terkelola.</h1>
        <p className="intro-copy">Satu tempat untuk membangun inventaris dan audit perangkat IT Anda.</p>
      </div>
      <p className="intro-foot">SPRINT 0 <span>Fondasi & akses pengguna</span></p>
    </section>
    <section className="login-panel"><div className="form-card">
      <p className="eyebrow">SELAMAT DATANG</p><h2>Masuk ke workspace</h2>
      <p className="muted">Gunakan akun yang diberikan administrator Anda.</p>
      <LoginForm />
      <p className="footnote">Akun hanya dibuat oleh administrator. Pendaftaran publik tidak tersedia.</p>
    </div></section>
  </main>;
}
