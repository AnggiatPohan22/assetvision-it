# Sprint 1B-03 — CSV preview, commit dan export

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, pengujian, smoke, migration development dan preservasi data selesai; siap review.
Scope hanya Task 1B-03. Belum memulai UI 1B-04 atau hardening/seed 1B-05; belum commit/push.

## Review Task 1B-02

AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, spesifikasi Sprint 1B dan laporan 1B-02
dibaca terlebih dahulu, dilanjutkan source aset/katalog, schema, service, seluruh migration,
auth/RBAC/CSRF, OpenAPI, proxy serta tests/runner Compose. Graph MCP list_projects dicoba
lebih dahulu; assetvision-it belum terindeks (hanya payload-cms-villa), sehingga fallback
inspeksi lokal dipakai tanpa membuat index/upload kode. Memory lookup tidak menemukan konteks proyek.

Working tree awal memuat 27 berkas perubahan 1B-01/02 yang belum di-commit; dipertahankan.
1B-02 sudah menyediakan CRUD unit/identifier, normalisasi, RBAC, version dan audit atomik.
Head development 0004_asset_registry. Gap: belum ada parser/report CSV, validasi batch,
receipt idempotency persisten, export aman, atau allowlist proxy CSV.
Rencana: parser/kontrak → ledger/migration additive → commit atomik/audit → router/export/proxy
→ pengujian/regresi/preservasi → laporan. Tidak mengubah invariant identitas/lokasi.

## Hasil implementasi

- POST /api/v1/assets/imports/preview menerima JSON csv_text. Parser CSV standar menerima
  comma/quoted delimiter/newline dan BOM UTF-8. Header wajib asset_code/manufacturer/model;
  optional serial_number/mac_address/hostname/condition/status/notes/location_hint. Header
  asing/duplikat/missing, CSV malformed, >500 row atau >256 KiB ditolak. Body JSON backend
  dan proxy dibatasi stream 1 MiB, juga tanpa Content-Length.
- Preview tidak membuat receipt/unit/claim/audit. Report per row berisi valid/error,
  duplikat code internal, code existing/reserved, unknown/inactive model, format identifier,
  collision DB dan internal CSV. Blank SN tidak membuat klaim atau placeholder palsu.
- Manufacturer/model diselesaikan berdasarkan nama kanonis case-insensitive. Tidak membuat
  katalog otomatis. Impor hanya menambah unit baru, tidak melakukan update/upsert/rename
  atau merge existing data, termasuk unit archived.
- Commit menerima ulang csv_text + UUID idempotency_key, memvalidasi ulang DB dan seluruh
  batch, serta mengunci referensi model. Payload preview client tidak dipercaya. Collision
  lintas unit/CSV memerlukan allow_identifier_collisions=true eksplisit; tidak membuat
  unique global baru atau menimpa klaim lain. Deteksi collision bukan reservasi global.
- Satu request adalah satu batch atomik: semua aset, klaim, snapshot audit dan receipt
  commit bersama atau seluruhnya rollback. Batch invalid mendapat 409 REJECTED,
  created_count=0, failed_count=total, report row/batch jelas. Konflik di tengah batch juga
  menghapus UUID/version sementara dari report. Tidak menyimpan receipt kegagalan.
- serial_number→SERIAL_NUMBER, mac_address→MAC_LAN, hostname→HOSTNAME, source IMPORT,
  verification UNVERIFIED. Audit CREATE dan IDENTIFIER_ADD menggunakan service snapshot
  1B-02; version unit dimulai 1 lalu naik untuk setiap klaim.
- Ledger asset_import_batches memakai UUID PK global, actor FK RESTRICT, SHA-256 CSV
  persis + flag collision, result JSONB dan waktu server. Unique key database menangani
  request bersamaan tanpa cache proses. Retry actor/payload identik mengembalikan receipt
  tanpa aset/audit tambahan; payload/actor berbeda 409. RBAC aktif tetap diperiksa sebelum
  replay. Receipt version adalah saat import, bukan latest version untuk mengedit.
- location_hint hanya staging pada report/receipt, tidak menjadi kolom aset, notes atau
  lokasi aktif. Tidak menyimpan CSV mentah pada database/berkas permanen.
- Export ADMIN satu row per unit, filter search/model_id/status existing, default termasuk
  ARCHIVED, tanpa pagination, maksimum 5000 unit/16 MiB. UTF-8 BOM, attachment assets.csv,
  private/no-store/nosniff. Semua klaim aktif ada dalam identifiers_json, termasuk banyak
  MAC dan tipe yang tidak mempunyai kolom scalar. Scalar SN/MAC_LAN/hostname memakai
  newline dalam quoted cell; soft-deleted claim dikecualikan. location_hint dikosongkan.
- Sel berawalan formula (=,+,-,@ setelah whitespace) atau tab/CR/LF diberi apostrof;
  CSV writer mengutip delimiter/newline/quote. Sanitasi tidak mengubah database. Export
  merupakan laporan dengan kolom tambahan, bukan format roundtrip import atau backup.
- Migration 0005_asset_imports hanya menambah ledger. Migration 0001–0004 tidak diedit.
  Readiness mengikuti head 0005 dan keberadaan ledger. Tidak menambah dependency/env,
  frontend page, Redis/cloud, foto unit, lokasi/movement atau AI/OCR.

## Berkas dikerjakan pada 1B-03

| Berkas | Perubahan |
|---|---|
| apps/api/app/asset_csv_schemas.py (baru) | Batas CSV/request, kontrak preview/commit/report |
| apps/api/app/asset_csv.py (baru) | Parser, validasi/collision, batch atomik, receipt replay |
| apps/api/app/asset_csv_routes.py (baru) | CsvRoute stream bound, ADMIN routes dan safe export |
| apps/api/app/asset_imports.py (baru) | Model ledger receipt sukses |
| apps/api/migrations/versions/0005_asset_imports.py (baru) | Additive ledger + index/FK/check, reversible |
| apps/api/app/asset_routes.py | Filter statement bersama list/export; perilaku CRUD dipertahankan |
| apps/api/app/main.py | Router CSV sebelum dynamic asset UUID |
| apps/api/app/models.py | Registrasi ledger pada metadata existing |
| apps/api/app/routes.py | Readiness head 0005 dan ledger |
| apps/api/app/openapi.py | Policy CSV dan dua bentuk error 409 |
| apps/api/tests/test_asset_csv.py (baru) | Parser/preview/commit/idempotency/export/RBAC/migration/concurrency |
| apps/api/tests/smoke_asset_csv.py (baru) | HTTP CSV proxy/API/PG nyata, data sintetis |
| infra/smoke-asset-csv.sh (baru) | Runner smoke terisolasi dan stop layanan uji |
| apps/api/tests/test_health.py | Head 0004 stale dan ledger missing → 503 |
| apps/api/tests/test_migrations.py | Head/tabel baru pada roundtrip existing |
| apps/api/tests/test_openapi.py | Kehadiran tiga route CSV dan kontrak CRUD existing |
| apps/web/lib/proxy.ts | Allowlist CSV dan limit body khusus impor 1 MiB |
| apps/web/tests/proxy.test.ts | Route/method/stream limit, konflik, export bytes/headers |
| README.md | Status CSV dan runner smoke |
| docs/API_CONTRACT.md | JSON/CSV input, reports, error, idempotency/export limits |
| docs/ARCHITECTURE.md | Ledger dan transaksi impor di monolith existing |
| docs/BUSINESS_RULES.md | Create-only, collision acknowledgement, staging, replay |
| docs/DATABASE.md | Schema/migration/downgrade ledger dan preservasi |
| docs/TESTING.md | Coverage/runner CSV |
| docs/sprints/SPRINT_1B_03_REPORT.md (baru) | Laporan ini |

Perubahan predecessor tetap ada; tidak mereset/staging/commit berkas lain, menyentuh .env,
menambah data nyata/foto ke Git, atau mengedit migration yang sudah diterapkan.

## Perintah aktual

Root Ubuntu WSL2 lewat PowerShell dengan prefix:
`wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it`.
Inspeksi source/dokumen menggunakan cat/head/grep setelah graph tidak mencukupi.

```bash
git status --short
docker compose exec -T api python -
# Fingerprint read-only awal dikirim via stdin; tidak membuat dump.
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff check --fix app/asset_csv.py app/asset_csv_routes.py \
  app/asset_csv_schemas.py app/asset_imports.py app/asset_routes.py app/routes.py \
  app/models.py app/main.py migrations/versions/0005_asset_imports.py
# Ruff check --fix/format juga dijalankan untuk test_asset_csv.py, smoke_asset_csv.py,
# modul CSV serta openapi.py pada iterasi terkait.
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_asset_csv.py tests/test_health.py \
  tests/test_openapi.py tests/test_migrations.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m ruff check .
bash infra/check.sh --postgres
# Ulang runner dari source final sesudah perbaikan satu baris format tes.
bash infra/check.sh --postgres
docker compose build api migrate web
bash infra/smoke-catalog.sh
bash infra/smoke-assets.sh
bash infra/smoke-asset-csv.sh
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps --wait api
docker compose up -d --no-deps --wait web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python -
# Fingerprint akhir dan probe HTTP read-only dikirim melalui stdin.
docker compose ps -a
docker compose config --quiet
git diff --check
```

Runner lengkap membangun api-test/web-check, pip check, pytest SQLite, Ruff, npm run check
(ESLint/tsc/tests), pytest PostgreSQL lalu stop db-test. Log di /tmp di luar repository.

## Hasil pengujian

| Pemeriksaan | Hasil yang sudah terverifikasi |
|---|---|
| Tes terarah awal SQLite | 57 passed, 2 skipped |
| Backend SQLite penuh final | **377 passed, 6 skipped** |
| Backend PostgreSQL/PostGIS penuh final | **383 passed**, runner exit 0 |
| Ruff final pada runner | All checks passed |
| Frontend | **38 passed, 0 failed**, ESLint dan TypeScript lulus |
| pip check | No broken requirements found |
| Build API/migrate/web produksi | Berhasil |
| Smoke katalog | Enam kelompok PASS, exit 0 |
| Smoke CRUD aset | Tiga kelompok PASS, exit 0 |
| Smoke CSV | Dua kelompok PASS, exit 0 |
| Alembic development current/check | 0005_asset_imports (head); No new upgrade operations detected |
| API/proxy ready | 200 / 200 |
| API/proxy assets/export.csv/auth/me anonim | 401 untuk semuanya |
| Development db/api/web | Healthy |
| Preservasi existing data/file | Identik, existingTablesAndFilesUnchanged=true |
| Compose config / git diff --check | Lulus / lulus |

Tes memeriksa preview fingerprint seluruh tabel, known/unknown/inactive/cross-manufacturer
model, duplikat code case-insensitive, code archived, collision DB/internal CSV, deleted claim,
SN kosong, source/verifikasi/normalisasi, key actor/payload/role, perubahan DB sesudah preview,
audit failure pada beberapa posisi di tengah batch dan rollback receipt/domain/audit,
CSV malformed/header/shape/quoted multiline, 500/501 row, UTF-8/body/stream limit,
RBAC/CSRF, safe export semua klaim/filter, dan roundtrip migration dengan domain nonkosong.
Tes PostgreSQL tambahan memakai session dan barrier independen untuk concurrent commit:
key sama menghasilkan receipt identik dan hanya dua unit/tiga event/satu receipt;
key berbeda dengan kode sama menghasilkan satu COMMITTED dan satu REJECTED, jumlah domain
dan audit sama tanpa parsial. Keenam skip SQLite adalah tes khusus PostgreSQL: JSONB,
lock katalog/foto existing, dua concurrency unit 1B-02, dan dua concurrency impor baru.
Semua berjalan/lulus pada PostgreSQL; tidak menutupi skip yang belum diverifikasi.

Smoke katalog memverifikasi login/cookie/SSR, CRUD/duplikat/filter/version/CSRF, lima foto
privat, input invalid/oversize, OFFICER/VIEWER denied, archive/history/delete/primary,
audit persisten dan cleanup kosong. Smoke aset mengulang CRUD/immutable code, SN kosong,
collision/search/soft-delete, role, logout dan enam tipe audit pada schema 0005.
Smoke CSV memakai HTTP Next.js/API/PG asli: preview tanpa menulis, dua unit sintetis
(termasuk tanpa SN), identifier, commit/replay identik, key payload conflict dan kode DB
existing ditolak, formula-safe export bytes/headers, hint staging, ADMIN-only/CSRF,
receipt dan audit tersimpan tanpa duplikat. Semua mutasi berada pada db-test/storage tmpfs,
dengan guard database/user existing. Tiap runner menghentikan stack smoke/db-test.
Tidak menjalankan browser manual atau smoke_stack.py terpisah; belum ada UI aset untuk direview.

Runner awal mencatat 377 passed/6 skipped SQLite lalu berhenti pada Ruff karena satu string
tes terlalu panjang; diperbaiki dan runner lengkap diulang. Iterasi lint juga memperbaiki
zip(strict=False), fixture re-export dan helper penggabungan nilai export. Tidak melonggarkan
constraint, menambah dependency atau mengubah invariant bisnis. Warning Starlette/httpx dan
Compose orphan smoke container existing tetap ada; tidak menghapus volume development.

## Preservasi dan verifikasi akhir

Sebelum perubahan runtime, seluruh tabel development dibaca dengan SET TRANSACTION READ ONLY,
diurutkan primary key lalu SHA-256 serialisasi deterministik. Path/hash bytes seluruh file
storage ikut difingerprint. Hanya jumlah/hash dicetak, tanpa isi baris/password/token/dump.
Migration development dijalankan setelah suite dan ketiga smoke lulus. Hanya menambah ledger,
lalu recreate API dan web dengan --no-deps; database container/volume existing dipertahankan.
Operasi recreate API sempat tertunda lama, kemudian selesai tanpa reset database atau
perubahan source tambahan. Seluruh rantai deploy/check akhirnya exit 0.
Tidak menjalankan downgrade, login, bootstrap, seed, import atau mutasi domain di development.

Fingerprint sesudah memakai program yang sama menghasilkan **existingTablesAndFilesUnchanged=true**:
seluruh 11 tabel aplikasi lama, spatial_ref_sys dan file storage identik. alembic_version
berubah 0004→0005 sesuai migration dan asset_import_batches baru berisi 0 row.
Jumlah tetap: users=1, auth_sessions=1, audit_events=5; tabel katalog/cleanup/aset kosong,
file foto=0, spatial_ref_sys=8500. Pengujian migration di DB uji juga mempertahankan isi semua
tabel existing, termasuk unit/identifier/audit nonkosong, melalui downgrade/upgrade ledger;
tes preservasi Sprint 0/1A existing ikut dijalankan ulang pada head 0005.

Probe read-only sesudah: API langsung dan proxy /ready 200; /assets, /assets/export.csv dan
/auth/me anonim 401 di kedua jalur. OpenAPI runtime langsung memuat ketiga route CSV.
Current/check Alembic lulus. Pemeriksaan akhir tidak membuat sesi atau audit baru.

## Batas dan risiko

- UI/import upload→preview→confirm belum dikerjakan (1B-04). Endpoint menerima csv_text JSON;
  client nantinya membaca file UTF-8 menjadi teks. Tidak ada multipart endpoint CSV.
- Seed delapan AP dan hardening sprint tetap 1B-05, tidak dimulai. Tidak ada auto-create model,
  update/upsert aset existing, foto unit, lokasi/movement atau AI/OCR.
- Receipt sukses disimpan tanpa pruning otomatis agar replay tetap tersedia. Backup DB
  harus mencakup ledger. Downgrade 0005 menghapus receipt/hint dan jaminan retry key lama,
  tetapi mempertahankan aset/identifier/audit; tidak dilakukan pada development.
- Collision adalah informasi saat validasi, bukan reservasi identifier terhadap writer lain.
  Serial tetap case-sensitive untuk collision sesuai 1B-01; search tetap case-insensitive.
- Export memakai pembacaan biasa, bukan snapshot global terhadap mutasi lain. Format laporan
  menyertakan sanitasi/kolom tambahan dan bukan backup atau input roundtrip importer.
- Error SQL/audit aman tidak membuka constraint/SQL/input internal. Akses database owner tetap
  dapat memodifikasi ledger; bukan ledger tamper-proof. Tidak ada API edit/delete receipt.

Review utama: asset_csv.py, asset_csv_routes.py, migration 0005 dan tests/test_asset_csv.py.
Berhenti pada 1B-03, tanpa commit/push atau memulai task berikutnya.
