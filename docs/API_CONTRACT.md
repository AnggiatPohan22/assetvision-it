# API Contract

Base path /api/v1. JSON; OpenAPI interaktif tersedia pada localhost:8000/docs.
Browser memakai localhost:3000/api/v1 melalui proxy allowlist.
Respons dari FastAPI memiliki Cache-Control: no-store dan X-Request-ID; proxy meneruskan keduanya dari upstream.

| Metode dan path | Otorisasi | Hasil |
|---|---|---|
| GET /health | Publik | 200 {"status":"ok"}; tidak mengakses database |
| GET /ready | Publik | 200 {"status":"ready"} atau 503 jika DB/PostGIS/skema tidak siap |
| GET /auth/csrf | Publik | 200 {"csrf_token":"..."} + cookie av_csrf untuk login |
| POST /auth/login | CSRF + Origin | 200 user + cookie sesi; 401 kredensial salah/akun nonaktif |
| GET /auth/me | Akun aktif, sesi valid | 200 user; 401 bila anonim/kedaluwarsa/dicabut |
| GET /auth/session | Akun aktif, sesi valid | 200 {"csrf_token":"..."}; 403 bila cookie CSRF sesi hilang/tidak cocok |
| POST /auth/logout | Akun aktif + CSRF sesi + Origin | 204; mencabut sesi dan menghapus kedua cookie |
| GET /admin/status | ADMIN | 200 {"status":"ok","role":"ADMIN"}; 403 untuk role lain |

User response: {"id":"UUID","email":"you@example.com","name":"Administrator","role":"ADMIN"}.
Tidak pernah menyertakan hash password atau access token dalam JSON.

Login body:
```json
{"email":"you@example.com","password":"your-local-password"}
```

Email maksimal 254 karakter, password login 1–1024 karakter.
Bootstrap membuat password 12–128 karakter. Tidak ada endpoint pendaftaran atau pengelolaan pengguna.

## Browser request sequence

1. GET /auth/csrf dengan cookie credentials same-origin; simpan csrf_token di memori sementara.
2. POST /auth/login dengan JSON, header X-CSRF-Token, dan Origin asli browser.
3. Cookie HTTP-only av_access dan av_csrf dikirim otomatis oleh browser.
4. GET /auth/me untuk identitas. Dashboard melakukan pemeriksaan ini di server.
5. GET /auth/session untuk token sesi, lalu POST /auth/logout dengan X-CSRF-Token.
6. Setelah 401, UI meminta login ulang. Setelah 403, UI menampilkan penolakan izin/keamanan.

CSRF berlaku pada semua metode selain GET/HEAD/OPTIONS, termasuk login.
Origin harus cocok persis dengan ALLOWED_ORIGINS. CLI HTTP juga harus menyertakan Origin.
Cookie token dan header harus cocok, bertanda tangan valid; untuk mutasi sesi hash-nya harus cocok dengan sesi database.
Tidak ada dukungan bearer token dari browser atau query string.
Endpoint anonim /auth/csrf ditujukan untuk login; setelah login gunakan /auth/session. Cookie CSRF yang signature-nya masih valid dipertahankan tanpa memperpanjang masa berlaku agar pemanggilan ulang tidak merusak logout sesi aktif. Login berhasil tetap merotasi token.

## Errors

Format kesalahan: {"detail":"pesan"}.
422 menggunakan array detail berisi loc, type, msg, tanpa submitted input.
401 berarti autentikasi diperlukan/tidak valid; 403 berarti role, origin, atau CSRF ditolak.
503 berarti dependensi belum siap; proxy menggunakan status ini saat API tidak dapat dihubungi.
Kesalahan internal menghasilkan 500 tanpa stack trace atau informasi database.
Proxy menolak path di luar allowlist dengan 404 dan metode yang salah dengan 405; body POST di atas 16 KiB ditolak 413. Batas diterapkan saat streaming, termasuk tanpa Content-Length; pembacaan dihentikan ketika batas dilewati. Body stream yang rusak ditolak 400.

Cookie development menggunakan HTTP-only, SameSite=Lax, Path=/, tanpa Domain.
COOKIE_SECURE=true wajib saat production dengan HTTPS. Token default 15 menit dan tidak diperbarui otomatis.
