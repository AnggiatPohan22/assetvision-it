# Sprint 2-01 — Location hierarchy

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, suite penuh, smoke, migration development dan preservasi selesai.
Scope hanya Task 2-01. Task 2-02 dan selanjutnya belum dimulai. Belum commit/push.

## Review hasil Sprint 1B

Repository awal bersih di main, HEAD/origin/main cc23283. Tiga commit Sprint 1B:
3f1f6ed (registry/CSV), 320c4c0 (frontend), cc23283 (hardening/seed sintetis).
Laporan 1B-05 yang menyebut belum commit/push adalah catatan saat task tersebut ditutup;
status Git aktual sudah sinkron. API/web/DB development healthy sebelum perubahan.

AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, spesifikasi/hasil Sprint 1B,
spesifikasi Sprint 2, migration 0001–0005, metadata/service/API aset dan CSV,
auth/RBAC/CSRF/audit, proxy, fixture/runner/Compose dibaca atau ditinjau.
Graph MCP list_projects dipanggil dahulu; AssetVision belum terindeks, sehingga discovery
beralih ke sumber lokal. Memory hanya membantu workflow bounded task, tooling test dan
preservasi; semua status Git/runtime/data dan hasil pengujian diverifikasi kembali.

Sprint 1B sudah menyediakan DeviceModel terpisah dari AssetUnit, kode aset immutable,
identifier tanpa placeholder SN, collision evidence, optimistic version, snapshot audit,
CSV replay ledger dan delapan contoh sintetis. location_hint masih staging receipt,
bukan lokasi resmi. Tidak perlu mengubah tabel aset atau mengulang seed untuk 2-01.
Gap terhadap task pertama Sprint 2: belum ada definisi hierarki lokasi, tree API,
constraint cycle, migration maupun tes hierarchy/concurrency.

Rencana: fingerprint read-only → skema/migration → API/query/tree/version/audit/guards →
tests positif/negatif dan race PostgreSQL → regresi penuh/build/smoke → migrasi development
dan fingerprint akhir → laporan. Tidak mengerjakan placement/movement task berikutnya.

## Implementasi dan keputusan

- `locations`: UUID tetap, parent_id self FK RESTRICT, code/name/kind, is_active,
  koordinat GPS opsional, actor/timestamps/version. Enam kind SITE/BUILDING/FLOOR/ROOM/AREA/SPOT.
  Tidak memaksakan matriks parent-kind universal karena hierarki outdoor/indoor bervariasi.
- Code lowercase ASCII 1–50 dengan separator hyphen, nama whitespace canonical maksimal
  200. Partial unique index menjamin kode per parent dan antar root, termasuk lokasi arsip.
  UUID update dan DELETE ditolak database. Arsip tidak cascade dan relasi tetap tersimpan.
- Latitude/longitude berpasangan dan bounded, accuracy nonnegatif maksimal 10 juta meter,
  gps_recorded_at berzona jika diberikan. Accuracy/time memerlukan koordinat. PATCH
  memvalidasi hasil gabungan sehingga partial clear tidak meninggalkan data GPS tak konsisten.
  Koordinat bukan bukti identitas aset. Floorplan/upload/pin opsional ditunda; API menolaknya.
- GET list/detail/tree semua role aktif; POST/PATCH ADMIN dengan sesi/Origin/CSRF existing.
  PATCH wajib version dan perubahan; sukses menaikkan version walaupun nilai sama.
  Archive/restore melalui is_active. Tidak ada hard-delete atau endpoint archive terpisah.
- Parent unknown 422, archived parent menolak child/reparent/restore baru 409; child historis
  tetap dapat diedit tanpa mengubah relasi. Arsip tidak menonaktifkan child otomatis;
  status active bersifat lokal, bukan agregat ancestor. Restore ke root/parent aktif boleh.
- PostgreSQL transaction advisory lock 649237804 diambil sebelum membaca hierarki/version.
  Ini menserialisasi seluruh mutasi hierarchy pada skala lokal. Trigger memakai key sama
  serta recursive CTE UNION untuk melindungi cycle SQL langsung. SQLite memakai trigger
  CTE dan constraint; pengujian concurrency multi-session memakai PostgreSQL READ COMMITTED.
- Audit memakai AuditEvent existing: location_create/update/archive dengan actor/time/id
  dan before/after JSON string di details, sesuai tipe dict[str,str] existing. Domain dan
  audit commit atomik; exception menggagalkan seluruh transaksi dan respons generik.
  Tidak ada API edit/delete audit atau klaim tamper-proof terhadap database owner.

## API

| Method | Route | Perilaku |
|---|---|---|
| GET | /api/v1/locations | Authenticated, filtering/pagination |
| GET | /api/v1/locations/tree | Authenticated, adjacency items+total termasuk arsip |
| GET | /api/v1/locations/{id} | Authenticated, detail/404 |
| POST | /api/v1/locations | ADMIN, 201 |
| PATCH | /api/v1/locations/{id} | ADMIN, version wajib, 200/409 |

List menerima parent_id (direct children), roots_only, kind, is_active, search name/code
literal case-insensitive, page 1–1 juta dan page_size 1–100 (default 20). Tanpa parent_id
membaca seluruh lokasi. roots_only tidak boleh bersamaan parent_id. Order code lalu UUID.
Tree berupa flat adjacency dengan parent_id, bukan JSON rekursif; menjaga ancestor arsip
dan tidak bergantung kedalaman JSON. Maksimal 5000 node; kelebihan menghasilkan 409 dengan
petunjuk memakai daftar paginated, tidak diam-diam memotong tree. Offset bukan snapshot
lintas request. Unknown field/query ditolak. Body JSON mutasi dibatasi stream 16 KiB pada
API dan proxy; non-JSON 415, oversize 413. Semua respons no-store/nosniff.

Frontend hanya menambah allowlist proxy dan tes forwarding/filter/version/method/size.
Belum ada UI lokasi pada 2-01; UI berada pada 2-05. Tidak ada asset current_location_id,
initial placement event, movement, timeline, observation, AI/OCR atau pemetaan hint otomatis.

## Migration

0006_locations hanya menambah tabel/index/constraint/trigger lokasi kosong. Migration
0001–0005 tidak diedit. Upgrade tidak menulis tabel existing, mengubah identity/version aset,
menambah seed atau menghapus data. Readiness mensyaratkan head 0006 dan keberadaan locations.
Tests predecessor yang mengharapkan head disesuaikan; kontrak CRUD/CSV aset tidak berubah.

Downgrade kembali 0005 dapat dilakukan saat locations kosong; bila berisi data, migration
menolak sebelum DROP. Pengujian roundtrip hanya pada database test. Tidak melakukan
downgrade/reset development. Tidak ada auto-create schema di startup aplikasi.

## Berkas berubah

| Berkas | Perubahan |
|---|---|
| apps/api/app/locations.py (baru) | Metadata domain dan constraints/index |
| apps/api/app/location_schemas.py (baru) | Input/output, version dan koordinat gabungan |
| apps/api/app/location_service.py (baru) | Lock, validasi ancestor, mutasi dan audit atomik |
| apps/api/app/location_routes.py (baru) | List/detail/tree/create/PATCH, bounded JSON |
| apps/api/migrations/versions/0006_locations.py (baru) | Migration dan database guards, safe downgrade |
| apps/api/app/models.py, main.py, routes.py, openapi.py | Registrasi metadata/router, readiness dan kontrak |
| apps/api/tests/test_locations.py (baru) | API/schema/preservasi/migration/SQL guards/concurrency |
| apps/api/tests/test_migrations.py, test_asset_csv.py, test_health.py | Head baru dan readiness regressions |
| apps/api/tests/smoke_locations.py (baru) | HTTP proxy/API/PG hierarchy dan role/logout |
| infra/smoke-locations.sh (baru) | Runner khusus lokasi, db-test tmpfs terisolasi |
| apps/web/lib/proxy.ts, tests/proxy.test.ts | Allowlist lokasi dan regresi transport |
| README.md, docs/API_CONTRACT.md, ARCHITECTURE.md, BUSINESS_RULES.md, DATABASE.md, TESTING.md | Kontrak/operasi/batas task |
| docs/sprints/SPRINT_2_LOCATION_MOVEMENT.md | Status hanya 2-01 dan acceptance parsial |
| docs/sprints/SPRINT_2_01_REPORT.md (baru) | Laporan hasil aktual |

## Perintah aktual dan iterasi

Perintah Ubuntu dijalankan melalui `wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it`.
Pembacaan berkas/graph, status/history dan review diff mendahului edit. Tidak mencetak .env,
password, token, nilai baris development atau dump database.

```bash
git status --short --branch
git log -3 --oneline
docker compose ps
docker compose exec -T api python -
# Program fingerprint read-only melalui stdin, hanya hash/count/bool dipublikasikan.
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff check --fix app/locations.py app/location_schemas.py \
  app/location_service.py app/location_routes.py app/routes.py app/models.py app/main.py \
  app/openapi.py migrations/versions/0006_locations.py tests/test_locations.py tests/test_migrations.py
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff format app/locations.py app/location_schemas.py \
  app/location_service.py app/location_routes.py app/routes.py app/models.py app/main.py \
  app/openapi.py migrations/versions/0006_locations.py tests/test_locations.py tests/test_migrations.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_locations.py tests/test_migrations.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m ruff check .
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_locations.py tests/test_migrations.py
# Diulang dengan --tb=short -x setelah perbaikan fungsi trigger dan transaksi fixture.
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff format tests/smoke_locations.py tests/test_locations.py \
  migrations/versions/0006_locations.py
bash infra/check.sh --postgres
# Run pertama berhenti pada Ruff pesan smoke terlalu panjang; runner penuh diulang.
bash infra/check.sh --postgres
docker compose build api web
docker compose config --quiet
bash -n infra/smoke-locations.sh
```

Awal lint menemukan import tak terpakai dan line length; format/fix dilakukan tanpa
melonggarkan aturan. Targeted SQLite lulus 48/3 skip. Targeted PG run pertama satu tes
lulus, 50 setup error karena fungsi trigger tersisa setelah fixture drop_all. Disamakan
dengan pola migration existing: CREATE OR REPLACE FUNCTION. Run berikutnya 43 lulus lalu
gagal pada test preservation karena inspeksi memulai transaksi yang belum di-commit setelah
upgrade. Fixture di-commit eksplisit; run final targeted PostgreSQL 51 passed.

Runner lengkap pertama SQLite 449 passed/10 skipped, lalu Ruff berhenti pada satu string
pesan smoke 109 karakter. String dipisah dan runner penuh diulang. Tidak menganggap exit
wrapper logging sebagai hasil sukses; hasil pemeriksaan di dalam runner menjadi acuannya.

## Validasi akhir

| Pemeriksaan | Hasil aktual |
|---|---|
| SQLite final | **449 passed, 10 skipped**, 103.42 detik |
| PostgreSQL/PostGIS final | **459 passed**, 146.52 detik |
| Frontend final | **58 passed, 0 failed**, termasuk satu regresi proxy lokasi baru |
| Runner lengkap final | `bash infra/check.sh --postgres`, **exit 0** |
| Ruff / ESLint / tsc / pip check | Lulus / lulus / lulus / No broken requirements found |
| Production build API/web | Berhasil, termasuk pemeriksaan TypeScript Next.js |
| Smoke predecessor | **20 kelompok PASS**, enam script Sprint 0/1A/1B, exit 0 |
| Smoke lokasi | **2 kelompok PASS**, proxy/API/PostgreSQL nyata, exit 0 |
| Migration development | **0006_locations (head)** |
| Alembic check development | **No new upgrade operations detected** |
| API dan proxy readiness | 200/200 |
| API/proxy locations, locations/tree dan assets anonim | Seluruhnya 401 |
| OpenAPI / batas task | Rute lokasi terdaftar; AssetPatch tetap tanpa current_location_id |
| Data tabel existing selain revision Alembic | **Identik** seluruh hash baris |
| Storage existing | **Identik**, tetap 0 file |
| Tabel baru | Hanya locations, **0 baris**, tanpa seed |
| Container DB development | **Sama** sebelum/sesudah; tidak direkreasi |
| Runtime akhir | API/web/db healthy; service smoke/db-test berhenti |
| Compose config / bash syntax / git diff --check | Lulus |

Sepuluh skip SQLite adalah tujuh tes PostgreSQL-only predecessor dan tiga race hierarchy
baru; seluruhnya berjalan pada PostgreSQL tanpa skip. Targeted race memeriksa dua session
independen, masing-masing satu sukses/satu konflik. Audit failure injection membuktikan
rollback lokasi dan audit; fingerprint read-only GET membuktikan tidak ada efek samping.
Fixture migration memuat seed predecessor lengkap sebelum roundtrip dan membandingkan
hash seluruh tabel; populated downgrade ditolak tanpa kehilangan definisi lokasi.

Regresi HTTP predecessor menjalankan bootstrap/idempotency, login/CSRF/session/logout,
SSR/role, CRUD katalog, lima foto privat/cleanup/audit, CRUD unit/identifier, CSV/replay/
export, riwayat metadata dan seed sintetis/replay. Smoke lokasi membuktikan Lounge, Lobby,
Villa 1, Villa 10 dapat dibuat sebagai children, tree/archive tetap terbaca, self/descendant
cycle dan stale version ditolak, OFFICER/VIEWER hanya membaca, serta logout mencabut akses.
Seluruh mutasi tersebut hanya di db-test tmpfs; runner dijalankan serial.

Perintah operasional tambahan yang benar-benar dijalankan:

```bash
bash infra/smoke-sprint1b.sh
bash infra/smoke-locations.sh
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps --wait api web
docker compose ps
docker compose logs --tail=12 api
docker compose exec -T api alembic current
docker compose build migrate
docker compose run --rm --no-deps migrate
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python -
# Fingerprint akhir, probe HTTP API/proxy dan OpenAPI melalui stdin, tanpa login/mutasi.
docker compose ps -q db
docker compose ps -a
git diff --check
git status --short
git diff --numstat
git diff --cached --stat
```

Pada penerapan development pertama, `migrate` memakai image miliknya yang masih lama:
build api/web tidak membangun image migrate. Akibatnya one-shot awal tidak menaikkan head
0005 dan API baru merespons readiness 503; web menunggu API. Diagnostik logs/current
menemukan mismatch, lalu image migrate dibangun ulang dan migrasi diulang. Head menjadi
0006, API/web healthy, up --wait serta current/check selesai exit 0. Ini mismatch image
operasional, bukan kegagalan DDL atau alasan untuk reset database. Image migrate kini
memuat revisi baru; container one-shot lama yang exited adalah catatan historis Compose.

## Preservasi development

Sebelum perubahan, seluruh 14 tabel termasuk spatial_ref_sys dibaca dengan
SET TRANSACTION READ ONLY. Seluruh kolom tiap baris (termasuk PK) diserialisasi deterministik,
di-hash SHA-256 lalu dibandingkan sebagai multiset per tabel. Storage dibandingkan dengan
path relatif dan hash bytes. Hanya count/bool dipublikasikan; tidak menyimpan dump/baris
development atau rahasia ke repository.

Sesudah migration dan pembaruan runtime, seluruh hash tabel existing identik kecuali
baris alembic_version yang memang berpindah 0005 → 0006. Storage identik. Satu-satunya
tabel baru adalah locations kosong. Users=1, auth_sessions=1, audit_events=8,
device_categories/manufacturers/device_models masing-masing=1, assets=8,
asset_identifiers=22, asset_change_events=30, spatial_ref_sys=8500 tetap persis.
Asset_import_batches, device_reference_images, storage_cleanup_jobs dan file tetap 0.

Hasil comparison: existingTablesUnchanged=true (revision Alembic dikecualikan secara
eksplisit), changedExistingTables=[], storageUnchanged=true, newTables=[locations],
newTableCounts.locations=0. Identitas container database development sama sebelum/sesudah.
Tidak ada login/bootstrap/seed development, reset, downgrade, penggantian environment,
perubahan password atau pemetaan hint. Tidak ada asset placement atau mutasi metadata
existing. Probe API/proxy akhir bersifat read-only. DB tetap hanya internal; API/web
bind 127.0.0.1:8000/3000. Tidak ada credential/data nyata/foto ditambahkan ke Git.

Migration 0001–0005, .env, dependency/lockfiles dan next-env.d.ts tidak berubah.
Semua perubahan task belum di-stage/commit/push; index kosong. Task 2-02 belum dimulai.

## Batas dan risiko

Tree berupa adjacency lengkap, bukan nested UI; lebih dari 5000 node memerlukan list
pagination. Serialisasi hierarchy memakai satu lock transaksi PostgreSQL, sesuai skala
lokal; writer SQL eksternal harus mengelola version/audit sendiri. Trigger mempertahankan
UUID/no-delete/cycle, bukan perlindungan terhadap database owner/superuser. Timestamp GPS
adalah bukti yang dimasukkan operator, bukan hasil GPS capture/geocoding atau verifikasi aset.

Tidak ada UI lokasi, floorplan/pin, FK lokasi aset, initial placement, movement, approval,
timeline/observasi atau AI/OCR. Tidak ada UAT visual/manual browser atau browser E2E yang
diklaim; tes frontend memakai Node/JSDOM dan smoke HTTP memakai stack nyata. Tidak ada
dependency security audit baru. Warning Starlette/httpx dan Compose orphan existing tetap
ada; web-smoke exit 143 berasal dari penghentian runner, sedangkan kedua runner exit 0.
Tidak ada langkah manual wajib tersisa untuk menutup 2-01; lokasi development masih kosong
agar operator dapat membuat definisi yang sesuai melalui API ADMIN. Berhenti pada task ini.
