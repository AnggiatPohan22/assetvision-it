# Sprint 1A-02 — CRUD API katalog perangkat

Tanggal: 18 Oktober 2026 (Asia/Makassar).
Status: selesai di working tree dan diuji; berhenti sebelum Task 1A-03.
Belum commit/push. Tidak ada upload/storage gambar, UI katalog, unit aset, OCR, atau AI.

## Review prasyarat

AGENTS.md, Sprint 1A, laporan 1A-01, README, ARCHITECTURE, BUSINESS_RULES, DATABASE,
API_CONTRACT, TESTING, migrasi, model, auth/RBAC, proxy, dan fixture pengujian diperiksa.
Working tree awal berisi hasil 1A-01 yang belum di-commit; perubahan tersebut dipertahankan.
Review dan regresi 1A-01 tidak menemukan masalah blocking. Query graph MCP dicoba lebih
dahulu tetapi assetvision-it belum terindeks; inspeksi dilanjutkan melalui file lokal.
Tidak mengulang indeks yang sebelumnya ditolak automatic approval review.

Database development awal masih `0001_sprint0`; tulisan `(head)` dari container API lama
merujuk migration tree image lama, bukan source terbaru. Ini diselesaikan sebelum API
baru memakai tabel katalog, menggunakan migrasi 0002 dari 1A-01 tanpa mengedit migrasi tersebut.
Tidak diperlukan migrasi tambahan untuk 1A-02.

## Perubahan perilaku

- List/create/detail/PATCH untuk device-categories, manufacturers, dan device-models.
- POST /device-models/{id}/archive mempertahankan baris, UUID, reservasi nama, dan referensi.
- Semua read memerlukan sesi aktif. Hanya ADMIN boleh mutasi; OFFICER/VIEWER menerima 403.
- CSRF/Origin, HTTP-only cookie, status akun, dan role memakai implementasi Sprint 0.
- PATCH/archive mewajibkan version positif; konflik versi awal maupun race ORM menghasilkan 409.
- Mutasi dan audit action/actor/table/id/version berada dalam satu transaksi; gagal audit rollback.
- Search nama/alias/manufacturer, filter kategori/manufacturer/environment/status, pagination
  1–100 item, dan urutan nama + UUID deterministik. Default mencakup aktif dan archived.
- Validasi Pydantic membatasi nama, URL, aliases, dan specs; unknown field ditolak.
- Referensi baru/ganti/restore harus aktif; metadata historis tetap bisa diedit tanpa reaktivasi.
- Error aman 401/403/404/409/422 dengan detail string atau metadata validasi tanpa input/SQL.
- OpenAPI mendokumentasikan response dan errors. Tidak ada endpoint DELETE master katalog.
- Proxy same-origin meneruskan route katalog yang di-allowlist, query string, dan PATCH body;
  batas body 16 KiB dipertahankan. Tidak ada perubahan halaman frontend.

Detail field, batas JSON, archive/restore, pagination, dan contoh body ada di API_CONTRACT.md.

## Berkas yang berubah pada 1A-02

| Berkas | Tujuan |
|---|---|
| apps/api/app/catalog_routes.py (baru) | Route CRUD, filter, pagination, RBAC, OpenAPI errors |
| apps/api/app/catalog_schemas.py (baru) | Request/response dan validasi bounded input |
| apps/api/app/catalog_service.py (baru) | Transaksi, optimistic concurrency, referensi, audit |
| apps/api/app/main.py | Registrasi router katalog |
| apps/api/tests/test_catalog_api.py (baru) | 88 kasus API, role, validasi, archive, race, audit, OpenAPI |
| apps/web/lib/proxy.ts | Allowlist katalog, query forwarding, PATCH body |
| apps/web/tests/proxy.test.ts | Tiga tes regresi proxy tambahan |
| README.md | Menjelaskan cakupan katalog yang kini tersedia |
| docs/API_CONTRACT.md | Kontrak aktual CRUD/error/pagination/version |
| docs/ARCHITECTURE.md | Modul CRUD dan audit transaksional |
| docs/DATABASE.md | Status migrasi development dan validasi CRUD |
| docs/sprints/SPRINT_1A_02_REPORT.md (baru) | Laporan ini |

Berkas schema/seed/migrasi dan tes 1A-01 tetap ada dalam working tree awal; tidak dianggap
sebagai implementasi baru 1A-02. Tidak mengubah manifest dependensi, lockfile, secret, atau data existing.

## Migrasi development dan pelestarian data

Build API/migrate baru berhasil. Migrasi dijalankan melalui
`docker compose run --rm --no-deps -T migrate python -` dengan program verifikasi via stdin:

1. Membuka `engine.begin()` (satu transaksi PostgreSQL).
2. Memasang lock_timeout 5 detik dan statement_timeout 30 detik.
3. Memeriksa revisi awal termasuk revisi yang diketahui.
4. Mengunci users/auth_sessions/audit_events dalam SHARE MODE selama verifikasi agar
   perubahan paralel tidak mengacaukan perbandingan; tidak mengubah baris.
5. Mengambil count dan fingerprint MD5 seluruh isi masing-masing tabel, diurutkan UUID.
6. Memanggil Alembic upgrade head dan Alembic check pada koneksi transaksi yang sama.
7. Membandingkan snapshot sebelum/sesudah, memeriksa revisi dan empat tabel katalog,
   kemudian commit. Kegagalan assertion akan rollback seluruh migrasi.

Hasil aktual:

```text
No new upgrade operations detected.
Development schema: 0001_sprint0 -> 0002_device_catalog
Existing rows unchanged: {'users': 1, 'auth_sessions': 1, 'audit_events': 5}
Row content fingerprints unchanged; Alembic metadata check passed
```

Fingerprint dihitung dengan `md5(coalesce(string_agg(row_to_json(t)::text, '|' ORDER BY id), ''))`
dan dibandingkan dalam memori; tidak mencetak isi tabel/password/token.
Setelah recreate layanan dan pemeriksaan HTTP read-only, count tetap 1/1/5;
device_categories/manufacturers/device_models/device_reference_images masing-masing 0.
Tidak ada seed development, reset password, bootstrap ulang, downgrade development,
penghapusan volume, atau pemanggilan CRUD yang menulis data development.

## Perintah yang benar-benar dijalankan

Dari root proyek di Ubuntu WSL2 (dipanggil melalui PowerShell/wsl):

```bash
git status --short
docker compose ps
docker compose exec -T api alembic current
docker compose --profile test build api-test web-check
docker compose build api migrate web
# Program migrasi/verifikasi transaksional melalui stdin, seperti dijelaskan di atas:
docker compose run --rm --no-deps -T migrate python -
docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
# Rebuild source final setelah kontrak OpenAPI diselesaikan:
docker compose --profile test build api migrate api-test
docker compose up -d --no-deps --wait api

# Suite final memakai source yang dikemas pada image, tanpa bind mount:
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose config --quiet
git diff --check
docker compose -f compose.yaml -f compose.test.yaml --profile test stop db-test
docker compose ps
```

Selama iterasi, pytest/Ruff juga dijalankan menggunakan image lokal dengan source API
dipasang read-only `-v /home/anggiatpohan/projects/assetvision-it/apps/api:/app:ro`.
Ruff format/fix hanya pada berkas CRUD baru dan main.py, memakai uid/gid pemilik checkout;
setelah itu image dibangun ulang. Targeted suite test_catalog_api.py final: 88 passed.

Pemeriksaan HTTP read-only memakai `docker compose exec -T api python -` dengan urllib:
API `127.0.0.1:8000` dan proxy `web:3000`; health/ready, tiga list anonim, serta OpenAPI.
Tidak ada login buatan atau mutasi terhadap database development pada pemeriksaan ini.

## Hasil pengujian final

| Pemeriksaan | Hasil aktual |
|---|---|
| Backend SQLite dari image final | **156 passed, 1 skipped** (inspeksi JSONB khusus PostgreSQL) |
| Backend PostgreSQL 16/PostGIS dari image final | **157 passed** |
| Alembic upgrade/check/downgrade/upgrade | Lulus pada kedua database uji terisolasi |
| ADMIN create/detail/update/archive; OFFICER/VIEWER read-only | Lulus |
| Anonim/akun nonaktif, CSRF/Origin, regresi login/RBAC Sprint 0 | Lulus |
| Duplikasi kapital/spasi, beda manufacturer, invalid input/parent, stale version | Lulus |
| Konflik antar-session, rollback bila audit gagal, no-op version | Lulus |
| Archive mempertahankan metadata gambar/referensi; restore memeriksa parent | Lulus |
| Search alias JSON/JSONB, Unicode, literal wildcard; filter dan pagination tie UUID | Lulus |
| Ruff / pip check | Lulus / No broken requirements found |
| Frontend ESLint / TypeScript | Lulus |
| Frontend proxy tests | **8 passed, 0 failed** |
| Build api-test/web-check, API/migrate, dan web produksi | Berhasil |
| Development Alembic current / check | 0002_device_catalog (head) / tidak ada operasi baru |
| HTTP API langsung dan proxy: health/ready | 200 untuk keduanya |
| HTTP API langsung dan proxy: tiga list katalog anonim | 401 untuk semuanya |
| Konfigurasi Compose / git diff --check | Exit 0 |

Seluruh tes yang menghapus/membuat tabel atau menulis data sintetis hanya memakai SQLite
in-memory atau db-test/assetvision_test terisolasi. Tidak diarahkan ke database aplikasi.
Database uji dihentikan setelah suite final selesai; layanan development db/api/web tetap healthy.

## Masalah, batasan, dan langkah review

Docker Hub kembali dapat dijangkau; seluruh build final berhasil. Mekanisme bind mount
aman dipakai untuk iterasi, tetapi hasil final tidak bergantung padanya. Lint awal menemukan
format impor/panjang baris; diperbaiki sebelum lint final. Tidak ada kegagalan tes tersisa.
Warning deprecation Starlette TestClient/httpx masih ada seperti Sprint 0.
Compose memperingatkan container smoke lama; tidak menghapusnya secara otomatis.

Audit saat ini mencatat action/actor/table/id/version/timestamp, bukan diff/snapshot field lengkap.
Pagination offset tidak menjamin snapshot lintas request bila ada mutasi bersamaan.
PostgreSQL lower mengikuti aturan database; SQLite bukan pengganti pengujian PostgreSQL untuk
semua aturan Unicode. Backend dan proxy sama-sama telah diuji untuk perilaku yang didokumentasikan.

HTTP development diverifikasi read-only; alur CRUD authenticated diuji di API TestClient dengan
database terisolasi, bukan melalui akun nyata development. Belum menjalankan end-to-end UI
katalog atau upload gambar karena keduanya di luar task ini.

Review yang disarankan:

1. Baca API_CONTRACT.md, terutama version wajib, default status list, batas specs, dan restore.
2. Review catalog_routes.py, catalog_schemas.py, catalog_service.py dan tes positif/negatifnya.
3. Ulangi dua perintah pytest serta npm run check di atas pada database pengujian terisolasi.
4. Periksa `/docs`, `/api/v1/ready`, dan login existing secara manual bila diperlukan;
   jangan reset akun atau menjalankan fixture pengujian pada database development.
5. Beri approval terpisah sebelum Task 1A-03. Task tersebut belum dimulai.
