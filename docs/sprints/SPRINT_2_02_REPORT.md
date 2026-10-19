# Sprint 2-02 — Asset location

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, pengujian penuh, smoke, migration development dan preservasi selesai.
Scope hanya Task 2-02. Task 2-03–2-05 tidak dimulai. Review akhir selesai; perubahan
ditutup dengan commit lokal atas permintaan pengguna, tanpa push.

## Review Task 2-01 dan rencana

Awal task: working tree bersih di main, HEAD fdbc3a7 (feat: implement Sprint 2-01
location hierarchy). Laporan 2-01 yang menyebut belum commit adalah status historis;
commit sudah ada saat review ini. API/web/db development healthy. AGENTS.md, README,
ARCHITECTURE, BUSINESS_RULES, Sprint 2/report 2-01, migration 0001–0006, metadata/service/
API aset dan lokasi, auth/CSRF/RBAC, runner/fixture dan proxy ditinjau. MCP graph list_projects
serta search_graph dipanggil dahulu; assetvision-it belum terindeks, sehingga discovery
beralih ke sumber lokal. Memori hanya membantu workflow WSL/test/data preservation;
status dan hasil aktual diperiksa ulang.

Hasil review: hierarki memakai FK, cycle/identity/delete guards, version, audit dan shared
hierarchy advisory lock; semantik is_active lokal (arsip tidak cascade ke child). Gap 2-02:
aset belum memiliki lokasi resmi, pencatatan penempatan awal atau lookup relasinya.
Tidak ditemukan kebutuhan mengubah domain/hierarki 2-01. Regresi suite lokasi termasuk
race PostgreSQL dijalankan bersama task ini. Fixture downgrade 2-01 disesuaikan untuk
melepas read lock sebelum migration successor mengubah FK aset.

Rencana dieksekusi: fingerprint read-only development → kolom nullable/migration →
service penempatan atomik dan lookup → tes negatif/positif, rollback/concurrency dan
preservasi migration → regresi/build/smoke terisolasi → upgrade development dan compare
fingerprint → laporan. Tidak mengerjakan movement state machine, timeline, observasi/UI.

## Implementasi dan keputusan

- assets.current_location_id UUID nullable FK locations.id, indexed, tanpa cascade;
  location_verified_at nullable. Response list/detail aset mendapat kedua field secara
  additive. Create/PATCH umum, CSV dan seed tidak menerima lokasi authoritative.
- GET /api/v1/assets/{id}/location semua role authenticated: asset_id, version,
  current_location_id, location_verified_at, location detail nullable. Aset unplaced 200
  dengan nilai null; unknown asset 404. Lookup tujuan memakai API lokasi 2-01 existing.
- POST /api/v1/assets/{id}/initial-placement ADMIN saja. Body version strict positif
  maksimal int32, location_id dan reason canonical nonblank maksimal 2000 karakter.
  Semua field ekstra termasuk timestamp/aktor ditolak. Origin/CSRF sesi existing wajib;
  stream JSON dibatasi 16 KiB di API/proxy. Bukan UI baru.
- Keputusan penempatan awal langsung oleh ADMIN; hanya untuk aset belum ditempatkan dan
  tidak archived, tujuan is_active lokal. Unknown tujuan 422; archived/stale/repeat/version
  limit 409. Retry tidak idempotent 201: jika pertama sudah commit, retry ditolak 409;
  client harus membaca ulang lokasi/version sebelum keputusan berikutnya.
- Lock order hierarchy advisory → row asset FOR UPDATE/populate_existing → baca tujuan.
  Hierarchy lock yang sama dengan 2-01 mencegah archive/penempatan memakai eligibility
  stale. Asset version menaik satu dan berkonflik dengan metadata/identifier yang stale.
- Satu transaksi menulis FK, location_verified_at UTC server, version dan INITIAL_PLACEMENT
  di tabel asset_events. Gagal insert event menggagalkan semuanya. Tidak mengubah status
  lifecycle, installed_at, model, identifier atau snapshot historis metadata.
- Event menyimpan actor_id, occurred_at, recorded_at dan correlation_id UUID unique;
  payload from=null, to UUID, snapshot lokasi, reason, expected/new version, effective_at
  serta keputusan ADMIN. Snapshot mempertahankan nama/status saat event meski lokasi
  kemudian diedit/diarsipkan. UPDATE/DELETE event ditolak trigger history existing.
- location_verified_at adalah waktu keputusan verifikasi awal ADMIN, bukan sensor GPS,
  bukti identitas tunggal, atau jaminan posisi fisik saat ini. Self-approval movement policy
  belum dipilih karena request/approval movement adalah Task 2-03.

## Migration dan preservasi

0007_asset_location menambah dua kolom nullable, index/FK, dan asset_events kosong.
Tidak mengubah migration 0001–0006 atau mengisi lokasi dari location_hint. PostgreSQL
FK default NO ACTION nondeferrable; SQLite ADD COLUMN REFERENCES tanpa rebuild tabel aset
existing. NO ACTION dipakai konsisten karena SQLAlchemy reflection SQLite tidak melaporkan
opsi ON DELETE RESTRICT pada inline ALTER ADD REFERENCES. Keduanya menolak orphan; DELETE
lokasi juga sudah ditolak trigger 0006. Metadata/Alembic check diuji kedua dialect.

Downgrade ke 0006 hanya bila seluruh FK/timestamp null dan asset_events kosong; jika ada
bukti lokasi, ditolak sebelum DROP. Roundtrip hanya di database test; development tidak
di-reset/downgrade. Readiness mensyaratkan head 0007, kolom aset dan tabel event terbaca.

Fingerprint awal disimpan di /tmp WSL di luar repository, hanya hash SHA-256 per baris,
count dan hash/path relatif file storage; tidak menyimpan dump/baris/rahasia. Seluruh tabel
termasuk PostGIS dibaca dengan SET TRANSACTION READ ONLY. Comparison akhir mengecualikan
hanya revision Alembic dan dua kolom baru dari hash proyeksi aset lama; kolom baru diverifikasi
null terpisah. Identitas container development DB juga dibandingkan.

## Berkas berubah

| Berkas | Isi |
|---|---|
| apps/api/app/asset_locations.py (baru) | Metadata event lokasi |
| apps/api/app/asset_location_service.py (baru) | Lock, initial placement, event atomik |
| apps/api/app/asset_location_routes.py (baru) | GET lookup, POST initial placement, input/output |
| apps/api/migrations/versions/0007_asset_location.py (baru) | Additive upgrade, retained history, safe downgrade |
| apps/api/app/assets.py, asset_schemas.py | FK/timestamp nullable dan response additive |
| apps/api/app/models.py, main.py, routes.py, openapi.py | Registrasi, readiness dan kontrak |
| apps/api/tests/test_asset_locations.py (baru) | Placement, auth, rollback, race, migration dan retention |
| apps/api/tests/test_health.py, test_migrations.py, test_asset_csv.py, test_assets.py, test_locations.py | Head/dependensi baru dan regresi predecessor |
| apps/api/tests/smoke_asset_locations.py (baru) | HTTP proxy/API/PostgreSQL sintetis |
| infra/smoke-asset-locations.sh (baru) | Runner db-test tmpfs terisolasi |
| apps/web/lib/proxy.ts, tests/proxy.test.ts | Dua route eksplisit dan transport/method tests |
| README.md, docs/API_CONTRACT.md, ARCHITECTURE.md, BUSINESS_RULES.md, DATABASE.md, TESTING.md | Kontrak dan operasi |
| docs/sprints/SPRINT_2_LOCATION_MOVEMENT.md, SPRINT_2_02_REPORT.md | Status bounded task dan hasil |

## Perintah aktual dan iterasi

Seluruh perintah Linux melalui wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it.
Akses WSL awal dalam sandbox ditolak E_ACCESSDENIED; invocation elevated yang direview
kemudian berhasil. Tidak memerlukan perubahan environment atau password. Pemeriksaan Git,
pembacaan sumber/graph, docker compose ps, config --quiet dan fingerprint read-only dilakukan.

```bash
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff check --fix .
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff format tests/test_asset_locations.py tests/smoke_asset_locations.py \
  app/openapi.py migrations/versions/0007_asset_location.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_asset_locations.py tests/test_migrations.py \
  tests/test_health.py --tb=short -x
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_asset_locations.py tests/test_migrations.py \
  tests/test_health.py tests/test_locations.py --tb=short -x
docker compose --profile test build api-test
bash infra/check.sh --postgres
docker compose build api web migrate
docker compose config --quiet
bash -n infra/smoke-asset-locations.sh
git diff --check
```

Ruff awal menemukan import/order, fixture import redefinition dan line length; diperbaiki
melalui source/formatter tanpa melonggarkan aturan. Targeted SQLite pertama 25 passed lalu
migration check gagal akibat inline FK reflection RESTRICT; definisi NO ACTION konsisten
menyelesaikannya. Targeted berikutnya 48 passed/2 skipped (sebelum tes archive race
ditambah). Targeted PostgreSQL sempat menunggu read lock pada fixture populated
downgrade predecessor; container test tersebut dihentikan spesifik (tidak DB development),
fixture rollback ditambah sebelum DDL. Tidak mengklaim targeted PG terinterupsi lulus.

Runner penuh pertama berhenti pada SQLite: 1 failed, 477 passed, 13 skipped. Assertion
Sprint 1B masih melarang current_location_id; diperbarui menjadi pemeriksaan dua field
nullable dan index. Runner penuh diulang. Build produksi API/web/migrate berhasil.

## Validasi akhir

| Pemeriksaan | Hasil aktual |
|---|---|
| Runner penuh final | `bash infra/check.sh --postgres`, **exit 0** |
| SQLite | **478 passed, 13 skipped**, 115.47 detik |
| PostgreSQL/PostGIS | **491 passed**, tanpa skip, 203.36 detik |
| Frontend | **59 passed, 0 failed** |
| Ruff / ESLint / TypeScript / pip check | Lulus / lulus / lulus / No broken requirements found |
| Production API/web/migrate build | Berhasil |
| Compose config / bash syntax / git diff --check | Lulus |
| Smoke regresi Sprint 0/1A/1B | **20 kelompok PASS**, exit 0 |
| Smoke hierarchy 2-01 | **2 kelompok PASS**, exit 0 |
| Smoke initial placement 2-02 | **2 kelompok PASS**, exit 0 |
| Migration development | **0007_asset_location (head)** |
| Alembic check development | **No new upgrade operations detected** |
| API/proxy readiness | **200/200** |
| API/proxy assets, locations dan lookup anonim | Seluruhnya **401** |
| Runtime akhir | API/web/db **healthy**, db-test dan smoke berhenti |
| Hash proyeksi kolom lama / storage | **Identik / identik** |
| Database container development | **Identik** sebelum/sesudah |
| Tabel event baru / aset ditempatkan development | **0 / 0**, tanpa seed/backfill |

Tiga belas skip SQLite adalah tes PostgreSQL-only, termasuk tiga race baru pada 2-02.
Semua berjalan pada PostgreSQL. Dua session independen membuktikan satu dari dua request
penempatan/version metadata sukses, lainnya 409; tidak ada lost update atau event ganda.
Race arsip memeriksa dua kemungkinan serial yang sah: placement sebelum archive (snapshot
aktif tetap ada), atau archive lebih dulu sehingga placement 409 tanpa event. Failure
injection event membuktikan rollback FK, timestamp/version dan seluruh data. Test migrasi
menggunakan delapan aset/22 klaim/30 event metadata sintetis; fingerprint predecessor
identik setelah roundtrip, kedua field lokasi null. Guard rewrite/delete dan orphan FK
diuji negatif. Regresi Task 2-01 termasuk cycle guards dan race hierarchy ikut lulus.

Warning Starlette/httpx existing dan pesan Compose orphan tetap muncul; tidak disembunyikan
atau dianggap kegagalan. Tidak melakukan upgrade dependensi dalam scope task ini.

## Smoke, operasi development dan hasil preservasi

Perintah tambahan yang benar-benar dijalankan setelah suite penuh selesai, berurutan:

```bash
bash infra/smoke-sprint1b.sh
bash infra/smoke-locations.sh
bash infra/smoke-asset-locations.sh
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python - < /tmp/av-20261019-2-02-fingerprint-after.py
# Output hash diarahkan ke /tmp, tidak mencetak baris/rahasia.
python3 /tmp/av-20261019-2-02-compare.py
python3 /tmp/av-20261019-2-02-probe.py
docker compose ps
git diff --check
git status --short
git diff --cached --stat
```

Seluruh smoke memakai db-test/assetvision_test tmpfs, bukan database development; runner
memastikan host/nama DB/user test. Regresi predecessor enam script mencakup bootstrap,
auth/CSRF/SSR, katalog/foto privat, registry/identifier, CSV/replay/export, UI/history guards
dan seed sintetis. Smoke 2-01 membuktikan hierarchy/cycle/archive dan role. Smoke 2-02 membuat
AP-003 sintetis → Villa 1 melalui proxy nyata, memeriksa event langsung di PostgreSQL
(aktor, asal null, tujuan, waktu dan correlation), stale/repeat 409, PATCH bypass 422,
lookup lokasi arsip untuk semua role, RBAC dan revokasi sesi. Semua runner exit 0; stopped
smoke containers bukan kegagalan pengujian. Tidak mengklaim penempatan AP-003 development.

Fingerprint comparison akhir: existingTablesUnchanged=true, changedExistingTables=[],
storageUnchanged=true, dbContainerUnchanged=true, newTables=[asset_events],
newEventCount=0, placedAssetCount=0. Hash seluruh baris tabel existing sama, dengan
pengecualian revision Alembic 0006 → 0007 dan kolom baru yang memang diperiksa terpisah.
Dua kolom baru null untuk seluruh 8 aset; current-location index/FK sudah diterapkan.
Counts tetap: users=1, auth_sessions=1, audit_events=8, assets=8, asset_identifiers=22,
asset_change_events=30, device_categories/manufacturers/device_models masing-masing=1,
spatial_ref_sys=8500. Asset_import_batches/device_reference_images/storage_cleanup_jobs/
locations dan storage tetap 0. asset_events baru juga 0.

Tidak melakukan login/bootstrap/seed/placement di development, reset/downgrade volume,
perubahan environment/password, atau pemetaan location_hint. Migration 0001–0006, .env,
lockfiles/dependensi dan next-env.d.ts tidak berubah. Probe akhir read-only: API/proxy
ready 200; assets/locations/lookup anonim 401; dua endpoint baru terdaftar di OpenAPI,
AssetCreate/Patch tetap tanpa field lokasi; movement/timeline/observation routes belum ada.
Runtime API/web/db healthy, database internal tanpa port host, API/web tetap loopback.
Pada akhir implementasi awal, seluruh perubahan belum staged/commit/push dan index kosong;
review serta commit lokal penutupan dicatat di bawah. Tidak ada langkah manual
wajib tersisa untuk menutup 2-02. Operator dapat membuat lokasi dan memutuskan penempatan
awal melalui API ADMIN secara eksplisit ketika diperlukan; development tetap unplaced.

## Batas

Tidak ada movement request/approve/reject, timeline/observation API, conflict badge, floorplan,
UI lokasi atau AI/OCR. Event awal adalah fondasi Task 2-04, tanpa membuka timeline lebih awal.
General PATCH/CSV tidak bisa mengganti lokasi; penempatan ulang menunggu Task 2-03.
Belum ada klaim UAT visual/browser E2E, load benchmark, atau audit keamanan dependensi baru.
History bukan tamper-proof terhadap database owner. Global hierarchy lock sesuai skala lokal.
Tidak melakukan push dan tidak memulai task berikutnya.


## Review akhir dan commit lokal

Atas permintaan pengguna, diff seluruh berkas tracked dan untracked Task 2-02 ditinjau
kembali sebelum staging. Tidak ada temuan yang menghalangi commit dan tidak ada perubahan
kode tambahan. Pemeriksaan mencakup role/CSRF, bounded JSON, FK/retensi, atomisitas event,
version/lock order, downgrade guard, proxy allowlist, tests dan konsistensi dokumen.
Hanya bagian laporan penutupan ini diperbarui setelah pengujian sebelumnya.

Log runner penuh dan tiga smoke diperiksa kembali: SQLite 478 passed/13 skipped,
PostgreSQL 491 passed, frontend 59 passed, smoke 20+2+2 kelompok PASS. Suite tidak diulang
karena kode tidak berubah: perbandingan byte di image api-test memastikan 71 berkas Python
(app/migrations/tests) identik dengan checkout; image web-check memastikan lib/proxy.ts
serta tests/proxy.test.ts identik. Tidak mengklaim suite tersebut dijalankan ulang saat review.

Fingerprint read-only diulang menjadi /tmp/av-20261019-2-02-review.json; `cmp` terhadap
fingerprint akhir implementasi menghasilkan exit 0. Data/storage dan kedua kolom nullable
aset tetap identik. `alembic current` masih 0007_asset_location (head); API/web/db healthy.
Tidak melakukan migrasi ulang, login, seed atau mutasi development selama penutupan.

Staging menggunakan daftar eksplisit 28 berkas Task 2-02 pada tabel berkas di atas,
termasuk laporan ini; tanpa `git add .`, environment, foto, dump, dependency/lockfile atau
next-env.d.ts. Pemeriksaan `git diff --check` dilakukan sebelum staging, dilanjutkan
`git diff --cached --check` dan review statistik/nama berkas staged. Commit penutupan:
`git commit -m "feat: implement Sprint 2-02 asset location"`. Status working tree dan
identitas commit diperiksa sesudahnya dengan `git status --short --branch` serta
`git log -1 --format=fuller --stat`. Tidak ada push atau implementasi Task 2-03.
