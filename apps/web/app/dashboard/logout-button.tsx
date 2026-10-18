"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
export default function LogoutButton() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function logout() {
    setBusy(true); setError("");
    try {
      const csrf = await fetch("/api/v1/auth/session", { cache: "no-store" });
      if (csrf.status === 401) { router.replace("/login"); router.refresh(); return; }
      if (!csrf.ok) throw new Error("Sesi keamanan bermasalah. Muat ulang atau masuk kembali.");
      const { csrf_token } = await csrf.json();
      const response = await fetch("/api/v1/auth/logout", {
        method: "POST", headers: { "X-CSRF-Token": csrf_token },
      });
      if (response.ok || response.status === 401) {
        router.replace("/login"); router.refresh(); return;
      }
      throw new Error(response.status === 403 ? "Permintaan ditolak. Muat ulang halaman."
        : "Belum dapat keluar. Silakan coba lagi.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Tidak dapat terhubung."); }
    finally { setBusy(false); }
  }
  return <div><button className="secondary" onClick={logout} disabled={busy}>
    {busy ? "Keluar…" : "Keluar"}</button>{error && <p role="alert" className="alert">{error}</p>}</div>;
}
