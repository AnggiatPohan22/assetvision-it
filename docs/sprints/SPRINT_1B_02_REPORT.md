# Sprint 1B-02 — CRUD API unit fisik dan RBAC

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, pengujian, verifikasi runtime dan preservasi data selesai; siap review.
Lingkup hanya Task 1B-02. Tidak memulai Task 1B-03 atau task berikutnya. Belum commit/push.

## Review Task 1B-01 dan kondisi awal

AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, spesifikasi Sprint 1B, laporan 1B-01,
model/schema, seluruh migration, autentikasi/RBAC/CSRF, API/service katalog, proxy,
OpenAPI, fixture serta runner Compose ditinjau sebelum perubahan. Graph MCP list_projects
dicoba terlebih dahulu: hanya payload-cms-villa terindeks, bukan assetvision-it. Karena
hasil tidak mencukupi, inspeksi lokal dipakai; tidak membuat index/upload kode baru.

Working tree awal memuat 14 berkas perubahan 1B-01 yang belum di-commit. Semua dipertahankan.
API/web/db development healthy pada 0004_asset_registry. Model AssetUnit/AssetIdentifier,
normalisasi, ORM version, snapshot audit dan trigger retensi sudah tersedia. Migration 0004
additive dan siap dipakai; tidak perlu migration baru atau modifikasi migration terpasang.

Gap yang ditutup: belum ada route CRUD/RBAC aset, version client, pencatatan audit otomatis
dalam transaksi domain, pencarian unit berdasarkan identifier, atau proxy allowlist aset.
Rencana: kontrak Pydantic → service transaksional → router/proxy → tes dan regresi → laporan.
Hasil lama 1B-01 bukan pengganti pengujian pada task ini; suite aktual dijalankan ulang.

## Implementasi dan keputusan

- CRUD unit: create/list/detail/PATCH/archive; code/UUID immutable dan tidak ada hard-delete.
  Create tidak membutuhkan SN; relasi model wajib valid dan aktif untuk pilihan baru.
  Referensi model archived existing tetap dapat dibaca dan metadata unitnya diedit.
- List memakai search, model_id, status, page/page_size. Search literal case-insensitive
  pada code dan identifier aktif; MAC lengkap berbagai notasi juga dikanonisasi. EXISTS
  mencegah satu unit muncul beberapa kali ketika banyak klaim cocok. Urut code lalu UUID.
- ADMIN dapat menulis; OFFICER/VIEWER membaca. Dependency autentikasi/role database serta
  Origin/CSRF existing dipakai kembali, tanpa sistem sesi paralel atau kredensial baru.
- Pydantic melarang field asing, code pada PATCH, null pada field wajib, version JSON
  bool/string, enum salah, teks melebihi batas, kontrol/surrogate, tanggal invalid dan
  installed_at tanpa timezone. Notes/tanggal opsional dapat dikosongkan secara eksplisit.
- Lock baris unit induk, baseline version client, dan ORM version mempertahankan concurrency.
  POST identifier memerlukan asset_version; PATCH/DELETE juga version identifier.
  Setiap perubahan klaim menaikkan version induk, sehingga form unit lama mendapat 409.
  Version maksimum 2147483647 ditolak sebagai limit sebelum overflow.
- Identifier API termasuk dalam task API: add/list/update/remove, merged type/raw validation,
  sumber/verifikasi, raw evidence dipertahankan, soft-delete dan larangan reparent/forged
  normalized value. Tidak membuat SN placeholder atau klaim kosong.
- Duplikat aktif dalam unit+tipe+normalized value → 409 aman. Collision lintas unit tetap
  boleh sebagai evidence dan respons collision_asset_ids menunjukkan unit lain bertipe/nilai
  sama, tanpa merge/overwrite. Collision lintas tipe tidak dianggap unik global.
- Snapshot CREATE/UPDATE/ARCHIVE/IDENTIFIER_ADD/UPDATE/REMOVE memakai tabel 1B-01, aktor sesi
  dan waktu server. Snapshot asset penuh; aksi identifier juga menyertakan klaim yang berubah.
  Domain, version dan audit berada dalam commit yang sama; gagal audit me-rollback semuanya.
  Tidak menghasilkan audit sukses untuk kegagalan validasi/RBAC/konflik.
- Archive berulang dengan version terkini adalah no-op; version lama 409. PATCH status ke
  ARCHIVED juga menghasilkan ARCHIVE. ADMIN dapat memulihkan status lewat PATCH; tidak ada
  workflow lifecycle baru. PATCH lain menaikkan version meski nilai sama, mengikuti katalog.
- DELETE identifier memakai query version/asset_version dan mengembalikan 200 beserta
  klaim terhapus dan version terbaru. Retry dengan kedua version terbaru no-op; baseline
  lama 409. Klaim terhapus tidak bisa dipulihkan lewat PATCH; pengganti memakai UUID baru.
- Proxy same-origin hanya membuka rute/metode eksplisit; cookie/CSRF, batas body 16 KiB,
  safe headers dan no-store existing dipertahankan. Tidak membuka import/export/foto unit.
- Helper pagination katalog hanya dilonggarkan generic type-nya agar menerima mapped entity
  aset; query/perilaku katalog tidak diubah. Tidak menambah dependensi atau environment.

## Berkas yang dikerjakan pada task ini

| Berkas | Perubahan |
|---|---|
| apps/api/app/asset_schemas.py (baru) | Kontrak bounded request/response aset/identifier/version |
| apps/api/app/asset_service.py (baru) | Lock/version, validasi model, snapshot audit atomik, collision |
| apps/api/app/asset_routes.py (baru) | Sembilan route CRUD aset dan identifier, RBAC, search/filter |
| apps/api/app/main.py | Registrasi router aset |
| apps/api/app/assets.py (existing 1B-01, belum tracked) | Pembaruan dua docstring sesuai service yang kini tersedia |
| apps/api/app/catalog_service.py | Pagination generic menerima entity aset; logika unchanged |
| apps/api/app/openapi.py | Deskripsi aset, ADMIN, version/asset_version |
| apps/api/tests/test_asset_api.py (baru) | CRUD/RBAC/CSRF/audit/validation/search/collision/concurrency |
| apps/api/tests/test_openapi.py | Kontrak rute, code immutable, baseline version, batas scope |
| apps/api/tests/smoke_assets.py (baru) | HTTP proxy/API/PG nyata dengan data sintetis terisolasi |
| infra/smoke-assets.sh (baru) | Build/run/stop smoke stack khusus DB/storage uji |
| apps/web/lib/proxy.ts | Allowlist CRUD aset/identifier |
| apps/web/tests/proxy.test.ts | Rute/metode, version query, deny CSV/delete unit, body limit |
| README.md | Status API dan perintah smoke aset |
| docs/API_CONTRACT.md | Request/response, role, error, version dan collision |
| docs/ARCHITECTURE.md | Service aset dan batas transaksi/concurrency |
| docs/BUSINESS_RULES.md | Policy identifier/archive/model/version/audit |
| docs/DATABASE.md | Skema tetap 0004 dan service API menggunakan tabel existing |
| docs/TESTING.md | Cakupan API/concurrency dan runner smoke aset |
| docs/sprints/SPRINT_1B_02_REPORT.md (baru) | Laporan ini |

Berkas 1B-01 lain dipertahankan tanpa perubahan task ini: app/models.py, app/routes.py,
tests/test_health.py, tests/test_migrations.py, migrations/versions/0004_asset_registry.py,
tests/test_assets.py dan laporan 1B-01. Tidak staging/commit/push atau mengubah .env/volume.

## Perintah yang benar-benar dijalankan

Dari root repository Ubuntu WSL2 melalui prefix PowerShell:
`wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it`.

```bash
git status --short
docker compose ps
# Inspeksi source/dokumen dan migration via cat/head/Select-String.
# Ruff check --fix dan format dijalankan pada modul/tes yang dikerjakan:
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff check --fix app/asset_schemas.py app/asset_routes.py \
  app/asset_service.py app/main.py app/openapi.py tests/test_asset_api.py \
  tests/test_openapi.py tests/smoke_assets.py
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff format tests/test_asset_api.py tests/test_openapi.py \
  tests/smoke_assets.py app/openapi.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_asset_api.py tests/test_openapi.py
bash infra/check.sh --postgres
# Sesudah koreksi format dan penambahan kasus: runner lengkap diulang.
bash infra/check.sh --postgres
docker compose build api web
bash infra/smoke-catalog.sh
bash infra/smoke-assets.sh
# Snapshot before/after dan probe read-only dikirim lewat stdin, tanpa menulis dump.
docker compose exec -T api python -
docker compose up -d --no-deps --wait api
docker compose up -d --no-deps --wait web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python -
docker compose ps
docker compose config --quiet
git diff --check
```

Ruff check/format juga dijalankan dengan subset berkas saat iterasi. Runner check.sh
membangun api-test/web-check, menjalankan pip check, pytest SQLite, Ruff, npm run check
(ESLint, tsc --noEmit, tests), lalu pytest PostgreSQL dan menghentikan db-test.
Output operasional disimpan di /tmp, tidak menyimpan credential/row data ke repository.

## Hasil pengujian aktual

| Pemeriksaan | Hasil final |
|---|---|
| Backend SQLite penuh | **334 passed, 4 skipped** |
| Backend PostgreSQL/PostGIS penuh | **338 passed** |
| Frontend tests | **37 passed, 0 failed** |
| ESLint / TypeScript | Lulus / lulus |
| Ruff | All checks passed |
| pip check | No broken requirements found |
| Build runtime API dan web produksi | Berhasil, termasuk Next.js TypeScript |
| Smoke katalog HTTP/SSR | Enam kelompok PASS, exit 0 |
| Smoke aset HTTP proxy/API/PG | Tiga kelompok PASS, exit 0 |
| Migration regression | Roundtrip/preservasi/model parity lulus dalam kedua suite |
| Development Alembic current/check | 0004_asset_registry (head); No new upgrade operations detected |
| Development API/proxy ready | 200 / 200 |
| Development API/proxy assets dan auth/me anonim | 401 untuk semuanya |
| Development db/api/web | Healthy |
| Fingerprint data/file before/after | Identik, allTablesAndFilesUnchanged=true |
| Compose config / git diff --check | Lulus / lulus |

Empat skip SQLite: dua existing khusus PostgreSQL (JSONB dan lock katalog/foto), serta
dua tes lock aset baru. Semua berjalan/lulus pada PostgreSQL. Dua tes baru memakai session
terpisah dan barrier untuk update/update serta update/identifier pada baseline sama;
hasil masing-masing tepat satu version 2 dan satu HTTP 409, tanpa audit sukses ekstra.

Tes rollback menyuntikkan kegagalan insert audit untuk enam jenis mutasi, kemudian membandingkan
unit, klaim, version dan jumlah audit sebelum/sesudah. Data domain dan audit tidak berubah.
Tes positif/negatif mencakup input immutable/asing, anon, OFFICER/VIEWER denied, akun nonaktif,
logout, CSRF/Origin, unknown/inactive model, historical model, duplikat aktif, collision,
partial type/raw update invalid, soft-delete/retry/replacement, MAC search, literal wildcard,
filter, pagination/empty result dan snapshot old/new.

Iterasi awal terarah: 35 passed, 1 skipped. Runner lengkap pertama: 325 passed, 3 skipped
SQLite, lalu berhenti pada Ruff karena dua string smoke terlalu panjang. String dipecah,
kasus validasi/concurrency ditambah, dan runner lengkap final **exit 0** dengan angka di atas.
Tidak ada pelonggaran constraint atau perubahan dependency. Warning deprecation Starlette/httpx
existing tetap muncul. Peringatan Compose orphan smoke container tidak ditindaklanjuti dengan
penghapusan volume/container development. Percobaan rg di WSL gagal karena binary tidak tersedia;
fallback pembacaan/Select-String dipakai. Satu upaya merapikan EOF lewat path PowerShell gagal
karena provider path; diperbaiki lewat patch dan diff check final lulus.

## Verifikasi runtime dan pelestarian data

Fingerprint awal diambil read-only dari seluruh tabel, termasuk tiga tabel aset, alembic_version,
spatial_ref_sys, serta path/hash bytes seluruh file storage. Program Python dikirim via stdin
ke container API; SET TRANSACTION READ ONLY, urut baris deterministik lalu SHA-256 JSON.
Hanya jumlah/hash yang dicetak, tanpa isi baris, password, token atau dump data.

Setelah build, hanya container API dan web development dibuat ulang menggunakan
`up -d --no-deps --wait`. Container database existing tidak diganti; volume postgres_data
dan reference_images tidak dihapus/ditulis ulang. Tidak menjalankan upgrade/downgrade baru,
login, bootstrap, seed atau mutasi domain di development.

Program fingerprint yang sama dijalankan pada API baru: **allTablesAndFilesUnchanged=true**,
meliputi seluruh 11 tabel aplikasi, alembic_version dan spatial_ref_sys serta storage.
Head tetap 0004. Jumlah before/after: users=1, auth_sessions=1, audit_events=5;
seluruh tabel katalog/cleanup/aset kosong, file foto=0; spatial_ref_sys=8500.
Readiness API langsung/proxy 200, assets/auth/me anonim keduanya 401. OpenAPI runtime
langsung memuat /api/v1/assets. Pemeriksaan ini read-only dan tidak membuat sesi/audit baru.

Smoke katalog memeriksa login/cookie/SSR, CRUD/filter/version/CSRF, lima foto privat,
invalid/oversize, seluruh mutasi OFFICER/VIEWER denied, archive/history/delete primary,
audit persisten dan cleanup kosong. Semua enam kelompok PASS.
Smoke aset memeriksa create tanpa SN, detail/PATCH/archive, immutable code, Origin/CSRF,
stale version, pencarian MAC lintas notasi, collision dua unit, identifier add/update/remove,
version baru, OFFICER/VIEWER read-only, logout, serta snapshot enam tipe event dengan aktor/waktu.
Seluruh mutasi smoke memakai DB/storage tmpfs terisolasi, tanpa data nyata. Kedua runner
menghentikan web-smoke/api-smoke/db-test pada akhir run. Tidak menjalankan browser manual
atau smoke_stack.py terpisah pada task ini; login/unauthorized diuji suite API dan HTTP smoke.

## Batas lingkup dan risiko tersisa

- CSV preview/commit/export, idempotency import, UI aset, foto unit dan seed delapan AP
  belum dikerjakan; tidak memulai 1B-03/04/05. Tidak ada lokasi/movement/AI/OCR.
- Audit snapshot tersedia dalam database, belum endpoint/UI audit. SQL writer di luar API
  masih wajib mencatat audit sendiri; trigger bukan perlindungan dari owner/superuser.
- Collision informasi saat baca, bukan uniqueness global atau reservasi terhadap transaksi
  lain. Pagination offset bukan snapshot lintas request. Serial case dipertahankan sesuai
  policy 1B-01; pencarian case-insensitive tidak mengubah aturan collision tersebut.
- Create unit dan add identifier adalah request terpisah; setiap request atomik. UI/import
  batch belum tersedia. Tidak ada retry otomatis saat 409; client harus reload/review.
- Validasi HTTP/SSR smoke tidak menggantikan review UI aset, karena UI belum masuk task ini.

Review utama: kontrak API, asset_service.py dan tests/test_asset_api.py. Tidak ada tindakan
manual untuk migrasi skema baru. Berhenti setelah laporan Task 1B-02; belum commit/push.
