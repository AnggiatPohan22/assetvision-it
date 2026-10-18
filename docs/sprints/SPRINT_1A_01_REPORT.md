# Sprint 1A-01 — Schema katalog perangkat

Tanggal: 18 Oktober 2026 (Asia/Makassar).
Status: implementasi dan pengujian selesai di working tree; menunggu review sebelum 1A-02.
Belum commit/push dan belum diterapkan ke database aplikasi.

## Inspeksi Sprint 0 dan gap

AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, DATABASE, API_CONTRACT, TESTING,
spesifikasi Sprint 1A, model, migrasi awal, autentikasi/RBAC, Compose, dan pola tes diperiksa.
Git awal bersih; layanan db/api/web healthy. Sprint 0 mempunyai satu metadata SQLAlchemy,
migrasi Alembic eksplisit, UUID aplikasi, audit autentikasi, dan fixture SQLite/PostgreSQL.
Belum ada tabel katalog, domain version counter, atau seed katalog. Readiness mengunci
revisi 0001_sprint0 sehingga harus disesuaikan bersama perubahan skema.

Graph MCP diutamakan, tetapi proyek belum terindeks. Automatic approval review menolak
index_repository karena berisiko mengirim kode privat ke tujuan graph yang belum terverifikasi.
Tidak ada upaya mengakali penolakan; inspeksi dilanjutkan melalui file lokal.

## Hasil implementasi

- Empat tabel: device_categories, manufacturers, device_models, device_reference_images.
- DeviceModel tetap terpisah dari unit fisik; tidak ada serial, lokasi, AI, atau storage file.
- Generated normalized keys, uniqueness manufacturer/model, CHECK nama kanonis/environment,
  indeks FK/model, JSONB PostgreSQL, dan FK tanpa cascade delete.
- Archive mempertahankan UUID dan reservasi nama. Satu primary reference image per model.
- Metadata gambar memeriksa ukuran positif, panjang hash, MIME allowlist, dan storage key relatif.
- Tabel master memiliki timestamps, actor FK nullable, dan version counter ORM.
- Migrasi baru 0002_device_catalog; migrasi 0001_sprint0 tidak diubah.
- Seed eksplisit/idempotent: lima kategori dan tiga manufacturer sintetis; tidak menimpa data lama.
- Readiness mensyaratkan revisi baru beserta tabel katalog. FK SQLite diaktifkan pada fixture.

## Berkas berubah

| Berkas | Perubahan |
|---|---|
| apps/api/app/catalog.py | Baru: model, enum, normalisasi, constraint/index/version |
| apps/api/app/seed_catalog.py | Baru: seed sintetis transaksional |
| apps/api/app/models.py | Mendaftarkan model katalog pada metadata yang sama |
| apps/api/app/routes.py | Memperbarui readiness skema |
| apps/api/migrations/versions/0002_device_catalog.py | Baru: upgrade/downgrade skema katalog |
| apps/api/tests/test_catalog.py | Baru: pengujian positif/negatif katalog dan seed |
| apps/api/tests/conftest.py | Mengaktifkan foreign key SQLite |
| apps/api/tests/test_migrations.py | Metadata check, roundtrip, preservasi user Sprint 0 |
| apps/api/tests/test_health.py | Regresi skema lama/tabel katalog hilang |
| docs/ARCHITECTURE.md | Modul katalog |
| docs/DATABASE.md | Skema aktual, batasan, seed, dan penerapan |
| docs/API_CONTRACT.md | Batas task schema; belum ada endpoint katalog |
| docs/sprints/SPRINT_1A_01_REPORT.md | Laporan ini |

## Perintah yang dijalankan dan hasil

Perintah berikut dijalankan dari root proyek melalui Ubuntu WSL2.
Inspeksi memakai git status --short, git diff, docker compose ps, dan pembacaan file lokal.

```bash
docker compose --profile test build api-test web-check
```

Build web-check berhasil dari cache. Build api-test gagal karena Docker Hub tidak dapat
dijangkau (network is unreachable). Dependensi tidak berubah; seluruh tes backend selanjutnya
memakai image api-test Sprint 0 yang tersedia dengan source terbaru dipasang read-only:

```bash
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/app:ro \
  api-test python -m pytest -q
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/app:ro \
  api-test python -m pytest -q
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/app:ro \
  api-test python -m ruff check .
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose config --quiet
git diff --check
docker compose -f compose.yaml -f compose.test.yaml --profile test stop db-test
docker compose ps
```

| Pemeriksaan final | Hasil aktual |
|---|---|
| Backend SQLite | 68 passed, 1 skipped (khusus inspeksi JSONB PostgreSQL) |
| Backend PostgreSQL 16/PostGIS | 69 passed |
| Alembic upgrade/check/downgrade/upgrade | Lulus dalam kedua suite pada database uji |
| Duplikasi kapital/spasi, beda manufacturer, FK, archive, metadata foto, stale update | Lulus |
| Seed diulang, edit/archive lama dipertahankan | Lulus |
| Login, unauthorized, RBAC Sprint 0 dan readiness | Lulus dalam suite backend |
| Ruff | All checks passed |
| pip check | No broken requirements found |
| Frontend ESLint / tsc --noEmit | Lulus |
| Frontend proxy tests | 5 passed, 0 failed |
| Compose config / git diff --check | Exit 0 |
| Database pengujian | Dihentikan setelah tes |
| db/api/web aplikasi | Tetap healthy memakai image Sprint 0 |

Kegagalan awal: format impor/panjang baris Ruff; percobaan --fix pada mount read-only;
constraint backslash storage key yang berbeda perilakunya pada PostgreSQL dan SQLite.
Semuanya diperbaiki di source dan pemeriksaan diulang. Dua suite final masih mengeluarkan
warning deprecation Starlette TestClient/httpx yang sudah ada. Compose memperingatkan
container smoke lama; container tersebut tidak dihapus.

## Batasan dan review/penerapan manual

Build ulang backend dari Dockerfile belum terverifikasi akibat jaringan; tes source baru
sudah terverifikasi menggunakan dependensi image lokal. Production build dan smoke HTTP stack
baru tidak dijalankan. Tidak ada upgrade/downgrade/seed pada database aplikasi.

Review migrasi dan DATABASE.md terlebih dahulu. Saat akan menerapkan, bangun API/migrate dari
source yang sama, jalankan migrasi, lalu ganti API secara terkoordinasi karena readiness lama
menolak revisi baru. Seed dijalankan eksplisit bila diinginkan. Downgrade menghapus data katalog;
pengujian destruktif hanya dilakukan pada database terisolasi.

Version counter saat ini melindungi update/delete ORM; pemeriksaan version dari client,
audit domain transaksional, validasi Pydantic JSON, kontrak error/RBAC CRUD, dan pagination
belum diimplementasikan. Upload/serve gambar juga belum ada. Semua itu mengikuti task sprint
berikutnya; 1A-02 tidak dimulai tanpa persetujuan pengguna.
