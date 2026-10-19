# Sprint 2-05 — Frontend & UAT

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, UAT browser, regresi penuh, smoke dan preservasi akhir selesai.
Scope hanya Task 2-05. Implementasi tidak memulai task/sprint berikutnya; commit lokal diotorisasi terpisah setelah review akhir. Tidak push.

## Review hasil Task 2-04

Awal: working tree bersih di main, HEAD d3a2b89807646021453b393b5d77d9721335cf8d,
empat commit lokal di atas origin/main. AGENTS.md, README, spesifikasi Sprint 2, ARCHITECTURE,
BUSINESS_RULES, laporan 2-04, kontrak/schema/migration 0006–0009, proxy, pola auth/React dan
test/runner existing ditinjau. MCP graph list_projects dicoba dahulu; assetvision-it belum
terindeks, sehingga inspeksi sumber lokal dipakai. Memori hanya membantu workflow bounded,
WSL dan isolasi tes; keadaan Git/runtime/data diperiksa langsung.

2-04 sudah menyediakan timeline terpadu, observasi linked/unlinked, review ADMIN dan proyeksi
conflict tanpa mutasi master. Laporan/commit penutupan mencatat SQLite617/PG639/frontend61,
smoke30 dan hash existing identik. Angka tersebut adalah bukti predecessor, bukan klaim tes
ulang 2-05. API existing cukup untuk frontend; tidak ditemukan alasan mengubah schema,
invariant, backend business service atau authorization.

Gap: belum ada tree/edit lokasi, initial placement/request UI, inbox ADMIN atau timeline/
observasi/conflict pada detail aset. Rencana: fingerprint read-only → UI reuse API/auth shell →
React tests/SSR smoke/build → UAT browser pada fixture tmpfs → regresi penuh/predecessor smoke →
update web development → fingerprint akhir → laporan. Floorplan/pin opsional tetap ditunda.

## Implementasi

- /locations authenticated: path/tingkat hierarkis SITE/AREA/BUILDING/FLOOR/ROOM/SPOT, search,
  empty/loading/error/recovery. ADMIN create/edit/reparent/archive/restore dengan version.
  Parent diri/descendant tidak ditawarkan; backend tetap menolak cycle. Archived node tetap
  terbaca. Checkbox Lokasi aktif + Simpan adalah keputusan eksplisit, tanpa hard-delete.
  Koordinat existing ditampilkan dan tidak dikirim/diubah oleh edit nama/parent/status.
- Detail /assets/{id}: lokasi resmi/waktu verifikasi, proyeksi status/conflict dari API,
  penempatan awal ADMIN hanya unplaced, movement request OFFICER/ADMIN untuk placed nonarchived,
  observasi linked OFFICER/ADMIN, history/request sendiri cancel, review evidence ADMIN dan
  timeline dengan filter sumber/pagination. Bukti tidak menimpa official location.
- /movements: server ADMIN gate, default PENDING/filter semua status/pagination. Sebelum
  keputusan, current asset + lima event histori harus berhasil dimuat. Snapshot from/to,
  alasan/requester/waktu dibandingkan dengan lokasi/version terkini. Stale atau archived
  asset/inactive target menonaktifkan approve; reject/cancel tetap mengikuti validasi API.
  Alasan keputusan wajib. Policy pilot ADMIN self-approval terlihat dan tidak diubah.
- Role/user UUID berasal dari server CatalogProvider existing (UUID context opsional baru).
  OFFICER hanya melihat cancel miliknya; VIEWER read-only. Semua keputusan tetap RBAC backend,
  sesi HttpOnly, Origin/CSRF dan proxy existing. Tidak menambah role/permission sistem.
- WriteForm membekukan snapshot version, synchronous in-flight guard dan busy fieldset.
  Tidak optimistically memindahkan lokasi. Hasil error/network/malformed menghentikan submit
  ulang, mempertahankan draft; pembatalan/reload eksplisit dibutuhkan sebelum form baru.
  Mutasi sukses membaca ulang data/status/history. Tidak ada retry atau version bump diam-diam.
- UI menampilkan ACK sebagai ditinjau yang tetap bukti aktif; DISMISS mengecualikan proyeksi
  tetapi mempertahankan sejarah. Stale observation tetap berbeda dari conflict. Payload audit
  lama hanya ditampilkan dalam details read-only, tanpa edit/delete atau penulisan ulang.
- Shell, navigasi, loading/error boundary, focus labels dan CSS mobile mengikuti desain existing.
  Tidak menambah library, service, environment runtime, dependency/lockfile atau migration.
  UAT_FIXTURE_PATH hanya variabel helper test-only pada runner, didokumentasikan di TESTING.

## Berkas perubahan

| Kelompok | Berkas/fungsi |
|---|---|
| Domain frontend | apps/web/lib/locations.ts: DTO, labels, path/descendants/tree traversal, bounded CSRF writer |
| UI lokasi | components/locations/location-manager.tsx dan shared.tsx: tree/editor/select/WriteForm |
| UI aset | components/locations/asset-location.tsx: official status, placement/request/evidence/review/history/timeline |
| UI movement | components/locations/movements.tsx: inbox, request list, ownership, preview/decision |
| Pages | app/locations dan app/movements (layout/page/loading/error) |
| Integrasi | components/assets/asset-detail.tsx, components/catalog/shared.tsx, app/assets/layout.tsx, app/catalog/layout.tsx, app/dashboard/page.tsx, app/assets/assets.css |
| Tests | apps/web/tests/locations-ui.test.tsx, apps/api/tests/smoke_location_ui.py, infra/smoke-location-ui.sh |
| Dokumentasi | README, API_CONTRACT, ARCHITECTURE, BUSINESS_RULES, DATABASE, TESTING, Sprint 2 status, UAT dan laporan ini |

## UAT browser aktual

`bash infra/smoke-location-ui.sh --uat` exit0: empat kelompok SSR/proxy PASS, kemudian fixture
browser pada localhost:3002. Guard db-test/assetvision_test/test_runner, akun role acak dan
AP-003/empat lokasi sintetis. Credential hanya file /tmp permission0600 dalam direktori0700,
bukan .env development, output runner atau Git. Tidak menggunakan akun development.

Melalui form browser: ADMIN membuat lantai di bawah Villa1 lalu arsip; initial AP-003 ke
Villa1/version2; OFFICER request ke Villa10 tetap official Villa1; ADMIN inbox meninjau
snapshot/current/history lalu approve → Villa10/version3; OFFICER observed Villa1 → conflict,
no auto-revert; ADMIN ACK → conflict tetap; VIEWER read-only, direct inbox Akses terbatas,
filter metadata hanya event CREATE; arsip asal mempertahankan snapshot/event; logout request
baru /locations redirect /login. SQL test read-only sesudahnya membuktikan requester/reviewer
berbeda, observation ACK/version2, 5 event lokasi/correlation unik +1 metadata dan official
Villa10/version3. Tidak melakukan mutasi SQL langsung untuk alur domain browser.

Visual diperiksa pada desktop dan 390×844; form tersusun vertikal dan document width375 <=
viewport390. Tidak ditemukan error JavaScript pada pemeriksaan console sebelum logout.
Screenshot sintetis (bukan data/foto asli):

- C:/Users/Anggi/.codex/visualizations/2026/10/19/01a151e4-88cb-75b2-900a-5070c03eed60/sprint-2-05-desktop.png
- C:/Users/Anggi/.codex/visualizations/2026/10/19/01a151e4-88cb-75b2-900a-5070c03eed60/sprint-2-05-mobile.png

Viewport dipulihkan, file credential fixture sementara dihapus setelah UAT, dan stack UAT
dihentikan sebelum suite PostgreSQL. Detail kasus dan cara
ulang ada di SPRINT_2_UAT.md. Hanya satu browser/dua ukuran viewport; bukan sign-off operator
bisnis, uji perangkat fisik/lintas browser atau audit aksesibilitas penuh.

## Pengujian dan iterasi

Pemeriksaan frontend awal lint/TypeScript dan 76 tests lulus. Ditambah dua tes keselamatan
pending submit/preview failure, targeted file locations-ui: **17 passed, 0 failed**. Satu
lint no-control-regex diperbaiki menggunakan codepoint check; satu baris smoke terlalu
panjang dipecah sebelum verifikasi penuh. Tidak mengubah dependency agar warning hilang.

Regresi penuh yang sudah selesai: SQLite **617 passed, 22 skipped** (190.91 detik),
pip check **No broken requirements found**, Ruff **All checks passed**, frontend lint dan
TypeScript **lulus**, frontend **78 passed, 0 failed/skipped** (17 baru +61 existing).
Build produksi web exit0, termasuk kompilasi/TypeScript Next.js. Source aplikasi identik
dengan build/UAT; dua tes tambahan diverifikasi pada image web-check runner penuh. Perbandingan
byte/hash 67 berkas app/components/lib/tests (TypeScript/TSX/CSS) terhadap image web-check
menghasilkan seluruhnya sama. Manifest hash lokal disimpan /tmp/av-2-05-verified-web-source.json.

PostgreSQL/PostGIS **639 passed, 0 skipped** (317.39 detik), full runner exit0. Seluruh
22 skip SQLite dieksekusi pada PostgreSQL, termasuk semua race Sprint 2 predecessor.
Warning Starlette/httpx dan pesan Compose orphan existing tetap dicatat; tidak mengubah
library atau menghapus service/data di luar scope untuk menyembunyikannya.

Enam runner smoke final seluruhnya exit0: Sprint0/1A/1B **20**, hierarchy **2**, initial
placement **2**, movements **3**, observations **3**, location-ui **4** kelompok PASS; total
**34**. Ini terpisah dari empat kelompok SSR smoke pada persiapan UAT --uat sebelumnya.
Semua dijalankan serial terhadap PG dan satu sama lain di db-test tmpfs, lalu test services
berhenti. Smoke predecessor memeriksa auth/CSRF/session/role, katalog/foto privat, registry/
identifier/CSV/seed sintetis, hierarchy/cycle/placement, approval/reject/cancel/stale,
observation/conflict/review/retensi; UI runner memeriksa page gates/navigation/logout nyata.

## Perintah yang benar-benar dijalankan

Dari Ubuntu WSL2, source/runtime diperiksa sebelum implementasi. Test tools memakai image
api-test/web-check, bukan runtime. Perintah format/lint memakai bind API /src sesuai pola
repo; output panjang disimpan /tmp lokal.

```bash
git status --short --branch
git diff --check
docker compose exec -T api alembic current
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py
# Hash awal disimpan ke /tmp/av-20261019-2-05-before.json
# Pengujian frontend:
docker compose --profile test build web-check
docker compose --profile test run --rm --no-deps web-check npm run check
docker run --rm --network none assetvision-it-web-check ./node_modules/.bin/tsx --test tests/locations-ui.test.tsx
docker compose build web
python -m ruff format tests/smoke_location_ui.py
python -m ruff check tests/smoke_location_ui.py
bash infra/smoke-location-ui.sh --uat
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test exec -T api-smoke python - < /tmp/av-2-05-uat-verify.py
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test stop web-smoke api-smoke db-test
bash infra/check.sh --postgres
docker compose up -d --no-deps --wait web
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py > /tmp/av-20261019-2-05-after.json
python3 /tmp/av-20261019-2-05-compare.py
python3 /tmp/av-20261019-2-05-probe.py
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose config --quiet
bash -n infra/smoke-location-ui.sh
bash infra/smoke-sprint1b.sh
bash infra/smoke-locations.sh
bash infra/smoke-asset-locations.sh
bash infra/smoke-movements.sh
bash infra/smoke-observations.sh
bash infra/smoke-location-ui.sh
docker compose up -d --no-deps --wait web
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py > /tmp/av-20261019-2-05-final.json
cmp /tmp/av-20261019-2-05-before.json /tmp/av-20261019-2-05-final.json
python3 /tmp/av-20261019-2-05-probe.py
docker compose ps
git diff --check
git status --short --branch
git diff --cached --stat
```

Tidak menjalankan dua writer/suite bersamaan pada db-test. JSdom tests yang terarah dapat
berjalan terpisah dari backend karena tidak memakai PostgreSQL. UAT browser memakai CUA UI
locators; tidak memakai browser console fetch/state injection sebagai pengganti UI.

## Data existing dan operasi development

Fingerprint sebelum edit meliputi semua baris/kolom tabel aplikasi, PostGIS spatial_ref_sys,
Alembic dan file storage; tidak mengeluarkan data mentah atau secret. Tidak ada seed,
login/placement/movement/observasi/review pada database development. Tidak ada migration baru
atau perubahan 0001–0009. Hanya web diperbarui setelah verifikasi; API/DB tidak perlu recreate.

Web development diperbarui dengan `docker compose up -d --no-deps --wait web` setelah build,
frontend checks dan UAT lulus, sementara regresi PG berjalan pada database test terpisah.
API/DB tidak di-recreate dan migration tidak dijalankan ulang. Alembic current tetap
**0009_observations (head)**; check **No new upgrade operations detected**.

Fingerprint sesudah update: **allTablesIncludingRevisionUnchanged=true**, changedTables=[],
storageUnchanged=true, dbContainerUnchanged=true. Tidak ada pengecualian tabel/kolom/revision.
Counts tetap users1/auth_sessions1/audit_events8/assets8/identifiers22/metadata_events30,
category/manufacturer/model masing-masing1, spatial_ref_sys8500. locations, asset_events,
asset_movements, location_observations, import_batches, reference_images, cleanup_jobs dan
file storage tetap0. Hash seluruh version/timestamp/kolom existing identik.

Probe anonim development: /assets, /locations, /movements **307 ke /login**; proxy ready200,
observation inbox401. Tidak login atau menulis data ke development untuk acceptance sintetis.
Setelah smoke selesai, web diselaraskan kembali dengan image final runner (source aplikasi
sama; build memuat dua tambahan tes), lalu fingerprint ulang dibandingkan byte dengan baseline
awal: **cmp exit0**, tanpa pengecualian termasuk revision. API/web/db healthy; test services
berhenti, DB internal tanpa port host dan web/API tetap loopback. Tidak ada perubahan domain
atau schema saat menyelaraskan web final.

## Batas dan tindak lanjut

Floorplan/upload/pin opsional tetap ditunda; GPS existing read-only pada UI dan dapat diisi
melalui API. Form observasi detail hanya linked; unknown/unlinked tetap didukung API 2-04,
tanpa auto-link/inferensi identitas. Tree maksimum5000 mengikuti API; traversal iteratif dan
index dipakai, tanpa klaim benchmark maksimum. Pagination offset bukan snapshot lintas request.
Review histori menggunakan lima event terbaru dengan link ke timeline penuh. Tidak ada AI/OCR,
recognition, controller, GPS tracking, backfill hint, cloud atau Sprint 3.
Pada akhir implementasi, 31 berkas masih unstaged dengan index kosong. Penutupan commit lokal mengikuti review di bawah.
Tidak ada temuan penghalang pada review akhir implementasi. Tidak ada langkah manual wajib
tersisa untuk verifikasi teknis Task 2-05; operator dapat meninjau UAT dan memulai penggunaan
lokasi secara eksplisit. Data development sengaja tetap tanpa lokasi/movement/observasi.
Task/sprint berikutnya tidak dimulai.


## Review akhir dan commit lokal

Review akhir 19 Oktober 2026 atas diff tracked dan 18 berkas baru tidak menemukan temuan
penghalang commit. Cakupan tetap 31 berkas Task 2-05; backend bisnis, migration, dependency,
.env dan next-env.d.ts tidak berubah. Snapshot/version, backend RBAC, CSRF, hasil mutasi tidak
pasti, retensi histori dan isolasi fixture ditinjau kembali.

Hash 67 berkas frontend masih identik dengan manifest hasil pengujian penuh. Log aktual
mengonfirmasi SQLite617/22 skip, PostgreSQL639, frontend78, pip/Ruff serta enam runner smoke
34 kelompok PASS. Suite penuh tidak diulang karena kode teruji tidak berubah; perubahan
penutupan hanya laporan ini. `bash -n infra/smoke-location-ui.sh` dan `git diff --check` lulus.
Fingerprint read-only baru `/tmp/av-20261019-2-05-review.json` identik byte dengan baseline
awal (`cmp` exit0), tanpa pengecualian. API/web/db tetap healthy dan DB tidak diekspos ke host.

Pengguna mengotorisasi commit lokal setelah review ini. Seluruh 31 berkas dipilih eksplisit,
diff staged diperiksa lalu dicommit dengan pesan `feat: implement Sprint 2-05 location and movement UI`.
Tidak push dan tidak memulai task/sprint berikutnya.
