# Sprint 0 — Final Review and Verification Report

Tanggal: 18 Oktober 2026, Asia/Makassar.
Status: fondasi Sprint 0 selesai; snapshot final ini disertakan dalam commit lokal.
Hash commit dapat dilihat melalui `git log -1 --oneline`. Push tidak dilakukan.

## Cakupan yang selesai

- Monorepo FastAPI/SQLAlchemy/Pydantic/Alembic dan Next.js App Router/TypeScript.
- PostgreSQL/PostGIS dengan volume persisten dan tanpa port database publik.
- Health/readiness, konfigurasi tervalidasi, dan logging JSON tanpa body/token/password.
- Pengguna UUID, hash Argon2id, JWT singkat dalam cookie HTTP-only, CSRF, serta RBAC backend.
- Sesi database yang dapat dicabut, audit autentikasi, dan bootstrap admin pertama yang idempotent.
- Login responsif, dashboard terlindungi, logout, serta proxy satu origin.
- Docker multi-stage, lockfile, target pengujian khusus, dokumentasi WSL2, dan skrip pemeriksaan.

Belum ada implementasi AI, OCR, kamera, inventaris aset, perpindahan aset, Redis, atau cloud.
Sepuluh domain invariant dalam AGENTS.md tetap dipertahankan.

## Hasil final review

Review dilakukan pada autentikasi/CSRF/RBAC, lifecycle sesi, batas proxy,
model dan migrasi, build/dependency/volume, dokumentasi, serta berkas calon commit.
Graph kode belum memiliki indeks proyek ini, sehingga source diperiksa langsung.

Temuan yang direproduksi dan diperbaiki sebelum commit:

1. GET /auth/csrf mengganti cookie sesi yang masih valid dan merusak logout.
   Cookie bertanda tangan valid kini dipertahankan tanpa memperpanjang expiry.
   Login berhasil tetap merotasi token; hash sesi tetap diperiksa pada mutasi.
2. Token CSRF non-ASCII menyebabkan TypeError pada perbandingan signature.
   Input tersebut kini menghasilkan 403, bukan error internal.
3. Proxy membaca seluruh body sebelum menerapkan batas 16 KiB.
   Batas kini diperiksa ketika stream dibaca; stream dibatalkan segera saat melebihi batas.

Dua tes regresi backend dan satu tes frontend gagal pada implementasi sebelumnya,
lalu lulus setelah perbaikan. Tidak ada temuan penghambat commit yang masih terbuka.

## Hasil pengujian source final

| Pemeriksaan | Hasil aktual |
|---|---|
| pytest SQLite | 39 passed; exit 0 |
| pytest PostgreSQL/PostGIS | 39 passed; exit 0 |
| Ruff | All checks passed |
| ESLint | Exit 0 |
| TypeScript tsc --noEmit | Exit 0; paket resmi typescript 5.9.3 |
| Frontend proxy tests | 5 passed, 0 failed |
| pip check | No broken requirements found |
| Build runtime API / migrate / web | Berhasil |
| Next.js production build 16.4.2 | Berhasil |
| npm audit --package-lock-only | 0 vulnerabilities |
| npm audit --package-lock-only --omit=dev | 0 vulnerabilities |
| Live Alembic current | 0001_sprint0 (head) |
| Live Alembic check | No new upgrade operations detected |
| db / api / web | Healthy setelah recreate API/web |
| Smoke bootstrap CLI | Pembuatan admin uji dan pemanggilan ulang idempotent lulus |
| Smoke API dan proxy nyata | Health/readiness, 401, login invalid, CSRF 403, dua cookie lulus |
| Smoke dashboard | Anonim diarahkan ke login; admin mendapat dashboard dengan nama/peran |
| Smoke RBAC dan logout | VIEWER mendapat 403 untuk admin API; logout 204; sesi berikutnya 401 |
| Smoke sesudah logout | Dashboard kembali mengarahkan ke login |

Backend masih mengeluarkan satu warning deprecation TestClient/httpx per suite.
Compose memberi pemberitahuan container smoke lama di luar konfigurasi aktif.
Keduanya bukan kegagalan pengujian.

Audit npm biasa sempat gagal dengan HTTP 400 dari endpoint advisory fallback.
Pemeriksaan ulang menggunakan lockfile kanonis berhasil untuk seluruh dependency dan runtime.
Tidak ada paket atau lockfile yang diganti hanya untuk menutupi kegagalan audit tersebut.

## Bukti admin dan uji browser

Admin pribadi telah dibuat oleh pemilik melalui prompt password tersembunyi.
Database aplikasi berisi satu pengguna aktif dengan role ADMIN.
Audit aplikasi telah memuat admin_bootstrap, login, dan logout.
Tidak ada password, JWT, hash password, atau ekspor database dalam laporan ini.

Pemilik melaporkan telah menguji login, dashboard, dan logout melalui browser.
Pemeriksaan browser oleh agen sebelumnya juga memverifikasi redirect dashboard anonim
dan penolakan kredensial invalid. Pengujian valid-login/logout otomatis di atas memakai
HTTP terhadap API + Next.js nyata; tidak diklaim sebagai suite browser headless.

## Perintah verifikasi

Dijalankan dari Ubuntu WSL2 pada direktori proyek:

```bash
bash infra/check.sh --postgres
docker compose build api migrate web
docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose run --rm --no-deps web-check npm audit --package-lock-only
docker compose run --rm --no-deps web-check npm audit --package-lock-only --omit=dev
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test up -d web-smoke
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test run --rm api-test python tests/smoke_stack.py
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test stop web-smoke api-smoke db-test
git diff --cached --check
```

Tes regresi yang terfokus juga dieksekusi sebelum perbaikan untuk membuktikan temuan.
Source final kemudian dibangun ulang dan seluruh suite diulang. Lihat [TESTING.md](TESTING.md)
untuk perintah individual dan pemisahan image runtime/pengujian.

## Integritas data dan commit

- Container PostgreSQL utama dan volume assetvision-it_postgres_data dipertahankan.
- Jumlah pengguna aplikasi tetap satu; tidak ada bootstrap ulang atau perubahan akun oleh review.
- Pengujian database hanya memakai db-test/assetvision_test pada tmpfs.
- Layanan pengujian dihentikan sesudah selesai; tidak ada penghapusan volume PostgreSQL aplikasi.
- .env dan .env.backup-sprint0 diabaikan Git dan tidak dimasukkan ke staging.
- Node modules, build output, cache, data/foto, dan backup tidak dimasukkan ke commit.
- Calon commit dipilih melalui daftar berkas yang sudah direview; pemeriksaan staging
  mencakup whitespace, path terlarang, dan pencocokan rahasia lokal tanpa mencetak nilainya.
- Repositori awal belum memiliki commit. Commit ini membukukan seluruh fondasi Sprint 0,
  termasuk AGENTS.md yang sudah ada; aturan bisnis dan engineering-nya dipertahankan. Akhir baris text dinormalisasi menjadi LF melalui .gitattributes, dan baris kosong berlebih di akhir .gitignore dirapikan.

## Berkas dalam snapshot Sprint 0

```text
.env.example
.gitattributes
.gitignore
AGENTS.md
README.md
apps/api/.dockerignore
apps/api/Dockerfile
apps/api/alembic.ini
apps/api/app/__init__.py
apps/api/app/bootstrap.py
apps/api/app/config.py
apps/api/app/db.py
apps/api/app/dependencies.py
apps/api/app/logging_config.py
apps/api/app/main.py
apps/api/app/models.py
apps/api/app/routes.py
apps/api/app/security.py
apps/api/migrations/env.py
apps/api/migrations/script.py.mako
apps/api/migrations/versions/0001_sprint0.py
apps/api/pyproject.toml
apps/api/requirements-dev.lock
apps/api/requirements-dev.txt
apps/api/requirements.lock
apps/api/requirements.txt
apps/api/tests/conftest.py
apps/api/tests/smoke_stack.py
apps/api/tests/test_auth.py
apps/api/tests/test_bootstrap.py
apps/api/tests/test_config.py
apps/api/tests/test_health.py
apps/api/tests/test_migrations.py
apps/api/tests/test_review_regressions.py
apps/web/.dockerignore
apps/web/Dockerfile
apps/web/app/api/v1/[...path]/route.ts
apps/web/app/dashboard/logout-button.tsx
apps/web/app/dashboard/page.tsx
apps/web/app/globals.css
apps/web/app/layout.tsx
apps/web/app/login/login-form.tsx
apps/web/app/login/page.tsx
apps/web/app/page.tsx
apps/web/eslint.config.mjs
apps/web/lib/auth.ts
apps/web/lib/proxy.ts
apps/web/next-env.d.ts
apps/web/next.config.ts
apps/web/package-lock.json
apps/web/package.json
apps/web/tests/proxy.test.ts
apps/web/tsconfig.json
compose.smoke.yaml
compose.test.yaml
compose.yaml
docs/API_CONTRACT.md
docs/ARCHITECTURE.md
docs/BUSINESS_RULES.md
docs/DATABASE.md
docs/SPRINT0_REPORT.md
docs/TESTING.md
infra/check.sh
infra/init-env.py
```

## Batas Sprint 0

Pengelolaan pengguna, reset password, pembatasan percobaan login, retensi sesi/audit,
akun database runtime terpisah, dan hardening deployment publik belum termasuk sprint ini.
Tidak ada fitur wajib Sprint 0 yang tertunda.

Aplikasi tetap tersedia di http://localhost:3000/login.
Untuk checkout baru, ikuti [README.md](../README.md), buat rahasia lokal dengan init-env.py,
jalankan Compose, lalu bootstrap admin hanya jika database pengguna masih kosong.
