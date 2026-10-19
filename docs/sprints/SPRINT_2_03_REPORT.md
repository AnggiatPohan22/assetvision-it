# Sprint 2-03 — Movement state machine

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, regresi penuh, smoke, migration development dan preservasi selesai.
Scope hanya Task 2-03. Task 2-04/2-05 tidak dimulai. Review akhir selesai; perubahan
ditutup dengan commit lokal atas permintaan pengguna, tanpa push.

## Review Task 2-02 dan rencana

Awal task: working tree bersih di main, HEAD b150f8a (feat: implement Sprint 2-02 asset
location), dua commit lokal di atas origin/main. API/web/db development healthy. Laporan
2-02 dan spesifikasi Sprint 2 dibaca, beserta AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES,
modul metadata/schema/service/routes/CSRF/RBAC/proxy, fixture/runner dan migration predecessor
terkait. MCP graph list_projects/search_graph dipanggil dahulu; assetvision-it belum
terindeks sehingga discovery beralih ke sumber lokal. Memori hanya membantu batas tugas,
workflow WSL dan pengujian terisolasi; status/data/hasil tidak diasumsikan dari memori.

2-02 menyediakan FK nullable, lookup dan penempatan awal ADMIN dengan event/version atomik.
General PATCH dan CSV tidak menerima current_location_id. Snapshot event immutable dan
hierarchy advisory lock dapat dipakai kembali; belum ada request/review movement.
Tidak ditemukan penghalang untuk melanjutkan; regresi 2-01/2-02 ikut diuji pada task ini.

Rencana: fingerprint read-only → tabel/migration baru → request/approve/reject/cancel +
read history/inbox → tes transaksi/RBAC/constraint/konkurensi → regresi penuh/build/smoke →
upgrade development dan perbandingan hash → laporan. Tidak mengerjakan timeline/observasi,
UI, AI/OCR, seed data development atau task berikutnya.

## Implementasi dan keputusan

- AssetMovement/asset_movements baru menyimpan asset, from/to lokasi FK, status, reason,
  expected_asset_version, requester/time, snapshot lokasi, reviewer/time/review_reason,
  approved_at/effective_at dan optimistic version. Migration 0008 additive tanpa UPDATE
  tabel existing. Metadata/auth/DB/session/transaction/audit existing tetap dipakai.
- OFFICER/ADMIN request dengan asset_version, to_location_id dan reason wajib canonical
  nonblank maksimal 2000 karakter. Origin/version disalin server dari asset terkunci;
  client tidak dapat memasok from/status/aktor/waktu. Request tidak mengubah asset version,
  lokasi atau timestamp verifikasi. Aset unplaced harus initial placement 2-02 lebih dahulu.
- Aset archived, tujuan sama/archived, stale version atau version limit 409; unknown tujuan
  422. Lokasi asal archived boleh ditinggalkan. Tujuan aktif lokal, sesuai semantik 2-01
  (ancestor archived tidak otomatis mengarsipkan child). Beberapa request PENDING boleh ada.
- ADMIN approve/reject. Cancel oleh ADMIN atau OFFICER pembuat. VIEWER hanya membaca history
  per aset/detail, tanpa inbox atau write. Sesi aktif/Origin/CSRF existing tetap diperiksa.
- Self-approval ADMIN **diizinkan untuk pilot**, agar satu ADMIN lokal dapat beroperasi.
  Setiap event mencatat requester/reviewer, flag self_approval dan policy ALLOWED_PILOT.
  Tidak membuat admin tambahan atau mengubah akun existing.
- PENDING hanya sekali menjadi APPROVED/REJECTED/CANCELLED; terminal final. Semua keputusan
  wajib movement version dan reason. Replay/stale movement 409 tanpa event duplikat.
- Lock order request: hierarchy → asset; review: hierarchy → movement → asset. Row lock
  populate_existing dan ORM version mencegah lost update; hierarchy lock sama dengan 2-01
  menserialisasi eligibility dengan archive/reparent. Metadata/identifier writer existing
  hanya mengunci asset dan tidak mengambil hierarchy lock dalam urutan terbalik.
- Approve memeriksa ulang asset version/origin/status dan tujuan aktif. Dalam satu transaksi
  memperbarui FK lokasi, location_verified_at, asset version +1, keputusan/version movement
  +1 dan MOVEMENT_APPROVED. reviewed_at=approved_at=effective_at waktu UTC server saat
  keputusan; tidak menerima backdate/jadwal. Status lifecycle, model, identifier, installed_at
  dan notes tidak berubah. Request lain stale tetap PENDING sampai ditutup dan dibuat ulang.
- Reject/cancel menyimpan keputusan dan event, tanpa mengubah kolom/version aset. Request
  stale/tujuan archived tetap dapat ditutup. Kegagalan event me-rollback seluruh perubahan.
- Event MOVEMENT_REQUESTED/APPROVED/REJECTED/CANCELLED memakai asset_events existing: actor,
  occurred_at/recorded_at, correlation UUID per event, movement_id, snapshot request/keputusan,
  asset version dan policy self-approval. Snapshot tujuan approval juga tersimpan agar rename/
  archive tidak mengubah bukti historis. Tidak membuka API timeline Task 2-04 lebih awal.
- DB checks mengikat status dengan null/non-null review/approval, alasan bounded/canonical,
  version dan destination berbeda. Trigger PostgreSQL/SQLite menolak insert terminal,
  perubahan request, transisi invalid, rewrite terminal dan DELETE. Tidak mengklaim guards
  menggantikan RBAC aplikasi atau melindungi dari database owner/superuser.

## API dan batas

| Method | Route /api/v1 | Role |
|---|---|---|
| GET/POST | /assets/{id}/movements | Authenticated read; OFFICER/ADMIN create |
| GET | /movements | ADMIN inbox/list |
| GET | /movements/{id} | Semua role authenticated |
| POST | /movements/{id}/approve, /reject | ADMIN |
| POST | /movements/{id}/cancel | ADMIN atau OFFICER pembuat |

Request JSON: {asset_version,to_location_id,reason}. Decision JSON: {version,reason}.
Create 201, decision 200 MovementOutput; auth/role 401/403, unknown asset/movement 404,
conflict 409, validation/unknown target 422. JSON stream maksimal 16 KiB di API/proxy;
non-JSON 415 dan oversized 413. Tidak ada PATCH/delete movement. List status opsional,
page 1–1 juta/page_size 1–100 (default 20); inbox juga asset_id. Order requested_at DESC
lalu UUID DESC; offset bukan snapshot lintas request. Unknown query/field ditolak.
Read endpoints tanpa side effect. Semua response no-store/nosniff. Frontend hanya proxy
allowlist dan tes transport; UI movement baru Task 2-05.

## Migration dan data

0008_asset_movements menambah tabel/index/check/trigger kosong, tanpa perubahan skema tabel
existing atau backfill. Migration 0001–0007 tidak diedit. Downgrade ke 0007 menolak sebelum
DROP bila ada request, apa pun statusnya. Roundtrip hanya database test. Readiness head 0008
serta tabel movement terbaca. Snapshot migration test mencakup seed predecessor dan initial
placement/event 2-02 yang sudah ada, bukan hanya database kosong.

Fingerprint awal membaca seluruh tabel development termasuk PostGIS dengan SET TRANSACTION
READ ONLY, menyimpan count dan SHA-256 seluruh baris deterministik di /tmp WSL di luar Git.
Storage dibandingkan melalui relative path/hash bytes. Tidak menyimpan dump, baris atau
rahasia ke repository. Comparison akhir mengecualikan hanya revision Alembic 0007 → 0008;
seluruh kolom existing termasuk FK/version/timestamp aset dibandingkan tanpa proyeksi.
Identitas container database development juga dibandingkan.

## Berkas berubah

| Berkas | Isi |
|---|---|
| apps/api/app/movements.py (baru) | Metadata status/request/decision dan constraints |
| apps/api/app/movement_schemas.py (baru) | Input/output dan filter paginated |
| apps/api/app/movement_service.py (baru) | Request/decision, lock/version dan event atomik |
| apps/api/app/movement_routes.py (baru) | API history/detail/inbox dan transisi |
| apps/api/migrations/versions/0008_asset_movements.py (baru) | Additive DDL, guards dan safe downgrade |
| apps/api/app/models.py, main.py, routes.py, openapi.py | Registrasi metadata/router, readiness dan kontrak |
| apps/api/tests/test_movements.py (baru) | API/invariants/RBAC/rollback/SQL guards/race/migration |
| apps/api/tests/test_health.py, test_migrations.py, test_asset_csv.py | Head/dependensi baru |
| apps/api/tests/smoke_movements.py (baru), infra/smoke-movements.sh (baru) | HTTP regression pada db-test tmpfs |
| apps/web/lib/proxy.ts, tests/proxy.test.ts | Route allowlist, method/body/auth forwarding tests |
| README.md, docs/API_CONTRACT.md, ARCHITECTURE.md, BUSINESS_RULES.md, DATABASE.md, TESTING.md | Perilaku dan operasi |
| docs/sprints/SPRINT_2_LOCATION_MOVEMENT.md, SPRINT_2_03_REPORT.md | Status bounded task dan hasil |

## Perintah aktual dan iterasi

Seluruh perintah Linux melalui wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it.
Status/log Git, Compose ps/config, sumber/graph dan fingerprint read-only diperiksa sebelum
perubahan. Ruff check --fix/format memakai api-test user 1000:1000 dengan mount sumber
/src; tests memakai mount read-only. Tidak mencetak .env, cookie/token/password atau data asli.

```bash
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_migrations.py tests/test_health.py --tb=short -x
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_movements.py tests/test_migrations.py --tb=short -x
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_movements.py tests/test_migrations.py \
  tests/test_asset_locations.py tests/test_locations.py tests/test_health.py --tb=short -x
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m ruff check .
docker compose build api web migrate
bash -n infra/smoke-movements.sh
docker compose config --quiet
git diff --check
```

Schema/readiness awal 23 passed. Iterasi lint awal memperbaiki import/order, line length,
format docstring/SQL dan daftar file eksplisit (wildcard app/movement*.py tidak diekspansi
di dalam container). Tidak melonggarkan aturan. Tes pertama berhenti pada assertion timestamp
SQLite naive vs waktu aware dari objek decision; nilai datetime UTC dibandingkan, tidak
mengubah implementasi PostgreSQL. Login reviewer memakai auth nyata pada fixture akhir.

SQLite dan PG berikutnya masing-masing 62 passed lalu fixture preservation gagal karena
seed belum di-commit sebelum rollback. Ditambah commit dan initial event predecessor untuk
menguji preservasi data lebih lengkap. Run berikutnya SQLite 65 passed/6 skipped dan PG
71 passed lalu tes version=0 gagal karena ORM secara otomatis memulai version=1. Tes itu
diubah menjadi insert SQL Core langsung agar benar-benar menguji database constraint.
Tidak mengklaim run yang gagal lulus. Seluruh eksperimen hanya pada DB test.

## Validasi akhir

Pengujian terarah final: SQLite **73 passed, 6 skipped**, 39.55 detik; PostgreSQL
**177 passed**, 123.84 detik, termasuk regresi 2-01/2-02, migration dan health.
Build produksi API/web/migrate berhasil. Pemeriksaan Compose config, shell syntax dan
`git diff --check` lulus.

| Pemeriksaan | Hasil aktual |
|---|---|
| Runner penuh | `bash infra/check.sh --postgres`, **exit 0** |
| SQLite | **550 passed, 19 skipped**, 153.82 detik |
| PostgreSQL/PostGIS | **569 passed**, tanpa skip, 239.25 detik |
| Frontend | **60 passed, 0 failed** |
| Ruff / ESLint / TypeScript / pip check | Lulus / lulus / lulus / No broken requirements found |
| Production API/web/migrate build | Berhasil |
| Compose config / bash syntax / git diff --check | Lulus |
| Smoke Sprint 0/1A/1B | **20 kelompok PASS**, exit 0 |
| Smoke hierarchy 2-01 | **2 kelompok PASS**, exit 0 |
| Smoke initial placement 2-02 | **2 kelompok PASS**, exit 0 |
| Smoke movement 2-03 | **3 kelompok PASS**, exit 0 |
| Migration development | **0008_asset_movements (head)** |
| Alembic check development | **No new upgrade operations detected** |
| API/proxy readiness | **200/200** |
| API/proxy assets, inbox dan history anonim | Seluruhnya **401** |
| Hash seluruh kolom/baris existing / storage | **Identik / identik** |
| Container database development | **Identik** sebelum/sesudah |
| Tabel movement baru | **0 baris**, tanpa seed |
| Runtime akhir | API/web/db **healthy**; db-test dan smoke berhenti |

Sembilan belas skip SQLite adalah tes PostgreSQL-only, termasuk enam race movement baru.
Semua berjalan pada PostgreSQL tanpa skip. Dua session independen membuktikan satu approve
sukses vs approve/reject/cancel kompetitor 409, dua request pending tidak dapat sama-sama
mengganti lokasi dari snapshot aset yang sama, dan metadata edit tidak hilang. Archive vs
approve menghasilkan salah satu urutan serial yang sah: approve sebelum archive dengan
snapshot aktif, atau archive lebih dulu sehingga approve 409 tanpa event approval.

Empat failure injection (request/approve/reject/cancel) membuktikan rollback seluruh
movement/asset/event. Migration roundtrip mempertahankan fingerprint delapan aset, 22 klaim,
30 snapshot metadata, lokasi dan initial placement/event predecessor. Tes SQL langsung
memverifikasi constraint, immutable request, terminal final, retention dan orphan FK.
Regresi penuh mencakup auth, katalog, registry/CSV/seed serta Task 2-01/2-02.

Warning Starlette/httpx existing dan pesan Compose orphan tetap muncul; tidak menyembunyikan
warning atau mengubah dependensi di luar scope. Tidak menganggap container smoke yang
berhenti lewat runner sebagai kegagalan pengujian.

## Smoke, operasi development dan preservasi akhir

Perintah runner penuh, smoke dan operasi development yang benar-benar dijalankan, serial:

```bash
bash infra/check.sh --postgres
bash infra/smoke-sprint1b.sh
bash infra/smoke-locations.sh
bash infra/smoke-asset-locations.sh
bash infra/smoke-movements.sh
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python - < /tmp/av-20261019-2-03-fingerprint.py
# Output hash diarahkan ke /tmp/av-20261019-2-03-after.json, bukan baris/rahasia.
python3 /tmp/av-20261019-2-03-compare.py
python3 /tmp/av-20261019-2-03-probe.py
docker compose ps
git diff --check
git status --short
git diff --cached --stat
```

Semua smoke dijalankan pada db-test/assetvision_test tmpfs dengan guard host/database/user
test, terpisah dari development dan serial terhadap suite PostgreSQL. Enam script regresi
predecessor memeriksa bootstrap/auth/CSRF/SSR, katalog/foto privat, registry/identifier,
CSV/replay/export, frontend role guards dan seed sintetis. Dua runner 2-01/2-02 memeriksa
hierarki/cycle/arsip dan penempatan awal/lookup/role/version. Runner movement membuktikan
AP-003 sintetis ditempatkan di Villa 1, OFFICER request ke Villa 10 tetap menyisakan lokasi
resmi Villa 1 sebelum review; ADMIN approve mengubah ke Villa 10 dan version 3. Stale/replay
409, reject/cancel mempertahankan aset, inbox/review khusus ADMIN, history semua role,
self-approval pilot dan arsip lokasi mempertahankan seluruh event. PostgreSQL menyimpan
4 request dan 9 event sintetis pada skenario smoke, dengan requester/reviewer UUID, asal/
tujuan/waktu/correlation dan policy yang benar. Logout mencabut akses. Runner exit 0 dan
layanan test dihentikan; tidak membuat AP-003 atau memindahkan aset development.

Fingerprint akhir: existingTablesUnchanged=true, changedExistingTables=[],
storageUnchanged=true, dbContainerUnchanged=true, newTables=[asset_movements],
newMovementCount=0. Seluruh kolom tabel existing termasuk assets.current_location_id,
location_verified_at, version dan updated_at identik, kecuali revision Alembic 0007 → 0008
sesuai rencana. Tidak perlu mengecualikan kolom aset karena migration 0008 tidak mengubahnya.

Counts tetap: users=1, auth_sessions=1, audit_events=8, assets=8, asset_identifiers=22,
asset_change_events=30, device_categories/manufacturers/device_models masing-masing=1,
spatial_ref_sys=8500. asset_events, locations, asset_import_batches, device_reference_images,
storage_cleanup_jobs dan storage tetap 0. asset_movements baru juga 0. Tidak melakukan
login/bootstrap/seed/initial placement/movement di development, reset/downgrade volume,
perubahan environment/password atau pemetaan hint. Migration 0001–0007, dependencies/
lockfiles dan next-env.d.ts tidak berubah. Tidak menambahkan data nyata/foto/rahasia ke Git.

Probe akhir read-only: API/proxy ready 200; assets/inbox/history anonim 401. Route movement
terdaftar di OpenAPI, MovementCreate hanya mewajibkan asset_version/to_location_id/reason;
AssetCreate/Patch tetap tanpa field lokasi; timeline/observation routes belum ada. API/web/db
healthy, DB internal tanpa port host, API/web tetap loopback. Pada akhir implementasi awal,
index Git kosong dan seluruh perubahan task belum staged/commit/push; review serta commit
lokal penutupan dicatat di bawah. Tidak ada langkah manual wajib tersisa untuk
menutup 2-03. Operator dapat melakukan movement eksplisit melalui API setelah definisi dan
penempatan awal yang sah; data development sengaja tetap tanpa lokasi/movement.

## Batas

Tidak ada timeline/observasi API, conflict badge, UI movement, floorplan atau AI/OCR.
Beberapa request pending boleh ada; stale perlu explicit reject/cancel dan request baru.
Self-approval pilot bukan pemisahan tugas dua aktor wajib. Semua keputusan langsung berlaku
saat approve, bukan scheduler/backdating. Global hierarchy lock sesuai skala lokal <500 aset.
Tidak ada klaim UAT visual/browser E2E, benchmark beban atau audit dependensi baru. Tidak
melakukan push dan tidak memulai Task 2-04/2-05.


## Review akhir dan commit lokal

Atas permintaan pengguna, seluruh diff tracked dan berkas baru Task 2-03 ditinjau sebelum
staging. Tidak ditemukan temuan penghalang. Review mencakup request immutable, transisi
terminal, FK/check/retensi/downgrade guards, lock order, version/origin stale, eligibility,
RBAC/cancel ownership/self-approval policy, CSRF/body limits, event rollback, proxy allowlist,
tests dan konsistensi dokumentasi. Tidak ada perubahan kode setelah verifikasi; laporan
ini saja dilengkapi dengan catatan penutupan dan penjelasan urutan perintah yang lebih tepat.

Log pemeriksaan sebelumnya dibaca ulang: SQLite 550 passed/19 skipped, PostgreSQL 569
passed, frontend 60 passed, dan smoke 20+2+2+3 kelompok PASS. Suite tidak dijalankan ulang
saat penutupan karena sumber yang di-review identik dengan image yang telah diuji:
perbandingan byte api-test terhadap checkout mencakup 78 berkas Python app/migrations/tests,
semuanya sama; web-check memastikan lib/proxy.ts dan tests/proxy.test.ts identik.

Fingerprint read-only diulang ke /tmp/av-20261019-2-03-review.json; `cmp` terhadap fingerprint
akhir implementasi menghasilkan exit 0. Seluruh data dan storage tetap identik; tidak
melakukan login, seed, movement atau migrasi ulang development. `alembic current` tetap
0008_asset_movements (head), API/web/db healthy. Pemeriksaan ini tidak mengubah data.

Staging memakai daftar eksplisit 25 berkas Task 2-03 pada tabel perubahan, termasuk laporan
ini; tanpa `git add .`, .env, foto/data nyata/dump, dependencies/lockfiles atau next-env.d.ts.
`git diff --check`, `git diff --cached --check` dan statistik/nama berkas staged ditinjau
sebelum commit lokal: `git commit -m "feat: implement Sprint 2-03 movement workflow"`.
Sesudahnya identitas commit dan status diperiksa dengan `git log -1 --format=fuller --stat`
dan `git status --short --branch`. Tidak ada push dan Task 2-04/2-05 tetap belum dimulai.
