# Sprint 1B-01 — Schema dan invariants unit fisik

Tanggal: 18 Oktober 2026 (Asia/Makassar).
Status: implementasi, migration development, dan pengujian selesai; siap review.
Berhenti pada Task 1B-01. Task 1B-02 dan task berikutnya belum dimulai. Belum commit/push.

## Review Sprint 1A dan keadaan awal

AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, DATABASE, API_CONTRACT, TESTING,
spesifikasi Sprint 1A/1B, laporan penutupan 1A-05 dan laporan frontend 1A-04 diperiksa.
Source katalog, autentikasi/RBAC, readiness, SQLAlchemy, ketiga migration existing,
fixture pengujian, tests katalog/migration/health dan Compose diperiksa sebelum perubahan.
Graph MCP list_projects dicoba dahulu: assetvision-it belum terindeks, sehingga fallback
inspeksi file lokal dipakai tanpa mengindeks/mengirim ulang kode.

Working tree awal bersih. API/web/db development healthy pada revision 0003_image_cleanup.
Sprint 1A menyediakan pemisahan katalog model, API/RBAC, version ORM, audit transaksional,
foto privat, UI, dan runner pengujian terisolasi. Tidak ditemukan blocker prasyarat 1B-01.
Laporan 1A-05 mencatat 219 passed/2 skipped SQLite, 221 passed PostgreSQL, 36 tes frontend;
angka lama tersebut bukan klaim verifikasi baru. Regresi dan smoke aktual pada task ini ada di bawah.

Gap awal sesuai 1B-01: belum ada tabel unit, klaim identifier, snapshot audit metadata,
atau database guard untuk Asset ID permanen. Rencana yang dikerjakan: model/migration tambahan,
invariant di ORM dan database, tests positif/negatif serta pelestarian data, lalu dokumentasi.

## Hasil implementasi

**Unit fisik:** AssetUnit memakai tabel assets terpisah dari device_models, FK RESTRICT,
UUID stabil, asset_code unik, lifecycle, kondisi, catatan, tanggal opsional, timestamps,
dan version ORM. Default lifecycle IN_STOCK dan kondisi UNKNOWN. Status lain: IN_USE,
MAINTENANCE, RETIRED, ARCHIVED; kondisi lain GOOD, DAMAGED, UNUSABLE. Belum ada workflow transisi.

Kode dikanonisasi uppercase ASCII, panjang 1–50, diawali huruf/angka lalu huruf/angka/_/-.
Migration memasang trigger yang menolak perubahan UUID/asset_code dan hard-delete aset,
termasuk dari SQL langsung. Archive tetap mempertahankan baris dan reservasi kode.
Model yang direferensikan tidak dapat dihapus. Tidak menambahkan kolom lokasi bebas.

**Identifier:** SERIAL_NUMBER, MAC_LAN, MAC_WLAN, BSSID, HOSTNAME, MANAGEMENT_ID.
Source wajib MANUAL/IMPORT/CONTROLLER, verification UNVERIFIED/VERIFIED/DISPUTED.
Raw evidence dipertahankan, normalized value dihitung ORM. MAC menerima notasi compact,
colon, hyphen, atau dotted dan disimpan AA:BB:CC:DD:EE:FF; format tidak sah ditolak.
Hostname lowercase; serial/management ID trim dengan case dipertahankan karena aturan
manufacturer/controller belum dipastikan. Trigger juga memeriksa nilai kanonis SQL langsung.

SN boleh tidak tersedia: unit tidak perlu baris SERIAL_NUMBER. Klaim kosong atau placeholder
SN UNKNOWN/N/A/NA/- ditolak. Raw/normalized value pada baris klaim dibuat wajib; ini lebih
ketat daripada nullable pada rancangan awal untuk mencegah baris identifier tanpa bukti.

Partial unique index mencegah duplikat klaim aktif dalam (asset_id, tipe, normalized value).
Nilai sama lintas unit/tipe tetap dapat disimpan; lookup index memungkinkan deteksi collision.
Belum ada tipe yang telah dibuktikan unik global, termasuk serial yang belum didisambiguasi
per manufacturer; tidak menerapkan global uniqueness atau merge otomatis. Penanganan collision
melalui response API/import menjadi pekerjaan task terkait, belum tersedia di 1B-01.
Soft-delete memakai deleted_at; DELETE fisik dan perpindahan UUID/pemilik klaim ditolak.
Klaim pengganti dapat dibuat dengan UUID baru tanpa menghapus bukti lama.

**Audit metadata:** asset_change_events menyimpan actor/asset FK wajib, tipe event,
before_json nullable, after_json wajib dan recorded_at server. Snapshot memakai JSONB pada PG,
JSON pada SQLite. UPDATE/DELETE audit ditolak trigger. Audit autentikasi/katalog existing
tetap pada audit_events. Tabel terpisah diperlukan untuk FK dan snapshot domain penuh;
tidak memperluas payload audit keamanan yang sudah ada.

Ini model/skema audit, belum service pencatatan otomatis. Tests menulis snapshot secara eksplisit
dalam transaksi bersama domain dan membuktikan rollback saat audit gagal. Task 1B-02 harus
menghubungkan event create/update/archive/identifier dan version client secara transaksional.
Version ORM menolak stale update aset maupun identifier; bulk SQL tetap harus mengurus version
sendiri, sesuai pola katalog. updated_at dikelola ORM, bukan trigger SQL umum.

**Migration/readiness:** 0004_asset_registry di atas 0003, tanpa mengedit migration lama.
Menambah tiga tabel, index, constraint dan trigger/function guard; tabel lama tidak diubah.
Definisi migration mandiri, tidak mengimpor model aplikasi yang dapat berubah.
Readiness memeriksa head 0004 dan ketiga tabel baru. Tidak menambah endpoint aset/allowlist proxy.

## Berkas berubah

| Berkas | Perubahan |
|---|---|
| apps/api/app/assets.py (baru) | Model/enums unit, identifier, audit; normalisasi; version ORM |
| apps/api/app/models.py | Registrasi metadata domain aset pada Base existing |
| apps/api/migrations/versions/0004_asset_registry.py (baru) | Additive migration, constraints/indexes, trigger PG/SQLite, downgrade |
| apps/api/app/routes.py | Readiness head 0004 dan tabel aset |
| apps/api/tests/test_assets.py (baru) | Schema/invariant, SQL langsung, collision, concurrency, audit dan preservasi |
| apps/api/tests/test_migrations.py | Head/tabel baru pada roundtrip existing |
| apps/api/tests/test_health.py | Schema lama dan tabel aset hilang menghasilkan 503 |
| README.md | Status schema 1B-01; API/UI aset belum tersedia |
| docs/ARCHITECTURE.md | Modul/schema aset dan batas audit service |
| docs/BUSINESS_RULES.md | Kontrak identifier, code, retensi, version, collision |
| docs/DATABASE.md | Schema, vocabulary, migration/deploy/downgrade, hasil preservasi |
| docs/API_CONTRACT.md | Readiness baru; belum ada endpoint aset |
| docs/TESTING.md | Cakupan pengujian schema aset |
| docs/sprints/SPRINT_1B_01_REPORT.md (baru) | Laporan ini |

Tidak mengubah dependensi, environment/secret, frontend source, migration lama,
storage provider, data katalog, akun, domain lokasi, atau konfigurasi volume/port.

## Perintah aktual

Dijalankan dari root repo Ubuntu WSL2 melalui PowerShell/wsl. Prefix pemanggilan:
`wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it`.
Inspeksi dokumen/source memakai Get-Content/rg setelah fallback graph di atas.

```bash
git status --short
docker compose ps

# Iterasi source: image test existing dengan mount khusus API.
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff check --fix app/assets.py app/models.py app/routes.py \
  migrations/versions/0004_asset_registry.py tests/test_assets.py tests/test_health.py \
  tests/test_migrations.py
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff format app/assets.py app/models.py app/routes.py \
  migrations/versions/0004_asset_registry.py tests/test_assets.py tests/test_health.py \
  tests/test_migrations.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_assets.py tests/test_migrations.py tests/test_health.py

# Runner awal membangun api-test/web-check, pip check, SQLite; berhenti di Ruff.
bash infra/check.sh --postgres

# Build dan pemeriksaan individual sesudah perbaikan.
docker compose --profile test build api-test api migrate
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
docker compose config --quiet

# Setelah memperbaiki ekspektasi DataError PostgreSQL: rebuild dan ulang.
docker compose --profile test build api-test
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m pytest -q \
  tests/test_assets.py tests/test_health.py tests/test_migrations.py
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
bash infra/smoke-catalog.sh

# Snapshot read-only sebelum/sesudah: program Python dikirim via stdin, tanpa dump data.
docker compose exec -T api python -
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps --wait api
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python -
docker compose ps
git diff --stat
git diff --check
```

Ruff check/format juga dijalankan dengan subset tiga berkas baru saat iterasi.
Smoke script membangun api-test/api/web, memulai stack terisolasi, menjalankan smoke_catalog.py,
dan menghentikan web-smoke/api-smoke/db-test saat exit. Tidak menjalankan smoke_stack.py
atau browser manual baru pada task ini; login/unauthorized tetap diuji API regression dan HTTP smoke.

## Hasil aktual

| Pemeriksaan | Hasil |
|---|---|
| Backend SQLite penuh | **290 passed, 2 skipped** |
| Backend PostgreSQL/PostGIS penuh, run final | **292 passed** |
| Tests terarah final SQLite | **82 passed** |
| Skips SQLite | Dua tes existing khusus JSONB PostgreSQL dan concurrency row-lock; lulus pada PG |
| Frontend | **36 passed, 0 failed** |
| ESLint / TypeScript | Lulus / lulus melalui npm run check |
| Ruff final | All checks passed |
| pip check | No broken requirements found |
| Build api-test/web-check/api/migrate | Berhasil |
| Build web dalam smoke | Berhasil memakai cache; source frontend tidak berubah |
| Smoke katalog HTTP/SSR | Semua enam kelompok PASS |
| Migration | Base/head roundtrip, 0003/head roundtrip, model check, preservasi delapan tabel lulus di SQLite/PG |
| Development Alembic | **0004_asset_registry (head)**; No new upgrade operations detected |
| Data/file development | Fingerprint seluruh delapan tabel dan file foto identik |
| API dan proxy web /ready | 200 / 200 |
| Anonim device-models dan auth/me development | 401 / 401 |
| db/api/web development | Healthy; database container existing tetap berjalan |
| Compose config / git diff --check | Lulus / lulus |

Suite SQLite penuh dijalankan dua kali dan tetap 290/2. Setelah perubahan terakhir yang hanya
memperbaiki ekspektasi error tes, suite terarah 82 serta suite PG penuh 292 diulang pada image baru.
Kode runtime/migration tidak berubah sesudah suite SQLite penuh final.

Smoke memverifikasi login/cookie/SSR, CRUD/duplicate/filter/version/CSRF, lima foto privat,
file invalid/oversize, OFFICER/VIEWER denied pada mutasi, archive/history, delete foto,
logout, audit persisten dan cleanup backlog kosong. Semua mutasi berada di DB/storage uji.

Masalah selama iterasi: Ruff menemukan baris panjang, kemudian diperbaiki.
Runner awal berhenti pada satu baris migration; pemeriksaan individual final semuanya lulus.
Run PG pertama menghasilkan 291 passed/1 failed karena varchar(50) overflow ditolak PostgreSQL
sebagai DataError sebelum CHECK/trigger, sementara SQLite memberi IntegrityError. Tes diperbaiki
untuk mengharapkan kelas error yang tepat per dialect; run final 292 passed. Tidak melonggarkan
constraint. Satu warning deprecation Starlette/httpx existing tetap ada. Compose memperingatkan
container smoke yang tidak termasuk konfigurasi normal; tidak menghapus container/volume otomatis.

## Pelestarian data development

Sebelum migration, seluruh baris delapan tabel lama dibaca dalam SET TRANSACTION READ ONLY,
diurutkan UUID, diserialisasi deterministik lalu dihitung SHA-256. File storage dibandingkan
dari relative path dan hash bytes. Tidak mencetak isi baris, password, token, atau dump.
Program sama dijalankan setelah upgrade dan recreate hanya API. Perbandingan fingerprint
menghasilkan **existingRowsAndFilesUnchanged=true**; revision berubah 0003 → 0004.

```text
users=1, auth_sessions=1, audit_events=5
device_categories=0, manufacturers=0, device_models=0, device_reference_images=0
storage_cleanup_jobs=0, reference files=0
assets=0, asset_identifiers=0, asset_change_events=0
```

Tidak menjalankan login/seed/mutasi domain di development. Tidak menghapus/recreate database
atau volume dan tidak menjalankan downgrade development. Migration hanya additive.
Fixture preservasi di DB uji juga mengisi seluruh delapan tabel lama dengan data sintetis
nonkosong (termasuk katalog, JSON, sesi, foto metadata dan cleanup), lalu membandingkan semua
kolom sebelum/sesudah upgrade dan downgrade/upgrade. Ini melengkapi pemeriksaan development
yang katalog/fotonya memang masih kosong. Stack smoke dan db-test dihentikan setelah selesai.

## Batas dan review manual

- Task 1B-01 selesai pada schema/invariants/migration/tests. API/RBAC aset, CSV, UI,
  foto unit, seed AP-001…AP-008, lokasi/movement dan AI/OCR belum dikerjakan.
- Audit otomatis dan pengecekan client version harus dihubungkan oleh task API berikutnya;
  model audit saja tidak memaksa setiap SQL writer membuat event.
- Global uniqueness identifier belum diputuskan; collision lintas unit tetap evidence,
  tanpa overwrite. Review vocabulary status/kondisi dan policy identifier pada dokumen domain.
- Trigger bukan ledger tamper-proof terhadap owner/superuser. Pemisahan privilege runtime/migrasi
  tetap batas existing. Bulk SQL tidak mendapat concurrency/version/timestamp otomatis.
- Downgrade 0004 menghapus seluruh data aset baru. Hanya dilakukan di DB uji pada task ini;
  operasi pada data nyata memerlukan backup dan approval.

Review utama: assets.py, migration 0004, tests/test_assets.py, dan kontrak di DATABASE/BUSINESS_RULES.
Development siap dipakai untuk review; belum ada tampilan/API aset karena di luar task ini.
Tidak memulai Task 1B-02 atau task berikutnya.
