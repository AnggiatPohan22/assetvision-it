"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export default function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    const data = new FormData(event.currentTarget);
    try {
      const csrf = await fetch("/api/v1/auth/csrf", { cache: "no-store" });
      if (!csrf.ok) throw new Error("Layanan belum tersedia. Silakan coba lagi.");
      const { csrf_token } = await csrf.json();
      const response = await fetch("/api/v1/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf_token },
        body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
      });
      if (response.status === 401) throw new Error("Email atau kata sandi tidak valid.");
      if (response.status === 403) throw new Error("Sesi keamanan tidak valid. Silakan coba lagi.");
      if (!response.ok) throw new Error("Gagal masuk. Periksa isian atau coba lagi.");
      router.replace("/dashboard"); router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Tidak dapat terhubung.");
    } finally { setBusy(false); }
  }
  return <form onSubmit={submit}>
    <label htmlFor="email">Email</label>
    <input id="email" name="email" type="email" autoComplete="username" maxLength={254}
      placeholder="nama@organisasi.id" required disabled={busy} />
    <label htmlFor="password">Kata sandi</label>
    <input id="password" name="password" type="password" autoComplete="current-password"
      maxLength={1024} required disabled={busy} />
    {error && <p className="alert" role="alert">{error}</p>}
    <button type="submit" disabled={busy}>{busy ? "Sedang masuk…" : "Masuk ke workspace →"}</button>
  </form>;
}
