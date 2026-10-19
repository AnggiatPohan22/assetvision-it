# Testing and development dependencies

## Task 2-01 — lokasi

Suite `tests/test_locations.py` memeriksa keenam kind, normalisasi, unique sibling/root,
tree adjacency termasuk archived ancestors, filtering/pagination/read-only, RBAC/CSRF,
input spoofing dan koordinat PATCH gabungan, rollback audit, SQL cycle/identity/delete guards,
preservasi seluruh tabel predecessor dan downgrade populated-table refusal.
Tiga race PostgreSQL: dua PATCH version sama, opposite reparent service, opposite reparent
SQL langsung; masing-masing satu sukses/satu konflik dan tidak membentuk cycle.

Jalankan `bash infra/check.sh --postgres` untuk backend SQLite + PostgreSQL/PostGIS,
migration check/roundtrip dan frontend lint/type/tests. `bash infra/smoke-locations.sh`
membangun runtime dan memeriksa API melalui Next.js proxy/PostgreSQL nyata dengan data
sintetis: Lounge/Lobby/Villa 1/Villa 10, tree/archive, conflict dan role/logout guards.
Runner merekreasi hanya `db-test` tmpfs, tidak menyentuh DB development; menghentikan
smoke/test services saat selesai. Jalankan serial setelah suite integrasi.
`bash infra/smoke-sprint1b.sh` tetap menyediakan regresi HTTP predecessor.
Tidak ada location UI/E2E visual pada task ini. Angka hasil aktual ada di laporan 2-01.

## Penutupan Sprint 1B — Task 1B-05

`bash infra/check.sh --postgres` menambahkan test_seed_assets.py dan test_asset_hardening.py:
tepat delapan unit satu model, SN contoh, SN absent, MAC search, 30 snapshot/22 klaim,
idempotent rerun, kode/UUID/identifier/model/category conflict, production/non-ADMIN/inactive
denied, CLI confirmation, preservation edit existing, rollback katalog/unit/claim saat audit
gagal di awal/tengah/akhir, dan concurrent seed PostgreSQL dengan dua session independen.
Hardening API memeriksa rantai enam event/version, actor/time/before/after, read-only history
semua role, private error 500/audit rollback, dan penolakan field server yang dipalsukan.
Tes frontend menambah missing crypto.randomUUID recovery, malformed success tidak dianggap
tersimpan, serta beforeunload saat hasil tidak pasti dan listener dilepas sesudah sukses.

`bash infra/smoke-sprint1b.sh` menjalankan enam script HTTP/CLI secara berurutan: smoke_stack,
smoke_catalog, smoke_assets, smoke_asset_csv, smoke_asset_ui, smoke_seed_assets. Runner
**membuat ulang hanya service db-test tmpfs** untuk baseline bootstrap, tidak database db
development atau volume pengguna. Jangan jalankan bersamaan dengan pengujian PostgreSQL lain.
Trap menghentikan layanan smoke/test pada sukses/gagal. Smoke seed memakai guard database
helper existing, memverifikasi CLI dua kali, exact-eight model, search SN/MAC, claim/audit
dan export melalui proxy nyata. Login smoke memakai akun/password acak sementara.

## Task 1B-04 UI registry

`bash infra/check.sh --postgres` mencakup tests/assets-ui.test.tsx: list/filter/pagination,
role baca, loading/empty/error/session, form create tanpa SN, immutable code/frozen version,
konflik draft, archive confirmation, identifier type/source/verification/parent+claim versions,
collision links dan soft-delete confirmation. Alur CSV menguji UTF-8/byte bound, row errors,
staging hint, collision acknowledgement, confirm/success, 409 REJECTED, pergantian file,
serta retry hasil tidak pasti memakai payload/key/flag identik. Tes komponen menggunakan
React DOM/JSDOM dan mocked fetch; bukan klaim browser E2E atau pemeriksaan visual.

`bash infra/smoke-asset-ui.sh` membangun produksi dan menjalankan HTTP terhadap Next.js/API/PG
nyata: anonymous redirect, ADMIN SSR/navigation, detail, audit read, server guard tambah/impor
untuk OFFICER/VIEWER, backend write denial, logout. Memakai helper database guard existing,
db-test tmpfs dan data sintetis; tidak mengubah DB development. Runner stop stack uji saat selesai.
Endpoint events ditest semua role, scope antar-aset, pagination, snapshot, urutan timestamp sama,
unknown/invalid query, missing unit/anonymous dan tidak adanya metode tulis; proxy GET-only.

Pengujian dijalankan di image khusus. `api` dan `web` adalah layanan runtime:
image API tidak memasang pytest, sedangkan image web hanya membawa keluaran Next.js standalone.
Menjalankan pytest/ESLint/tsc melalui `docker compose exec api/web` akan gagal karena alat development tidak berada di image tersebut.

## Perintah utama (Ubuntu WSL2)

```bash
cd ~/projects/assetvision-it
bash infra/check.sh
# Tambahkan suite PostgreSQL/PostGIS dan pemeriksaan migrasi di database sementara:
bash infra/check.sh --postgres
```

Script membangun target test/check sebelum menjalankan pemeriksaan, tanpa memasang paket sementara
pada container aplikasi. Pengujian PostgreSQL memakai db-test/assetvision_test dan menghentikan
db-test setelah selesai. Container dan volume database aplikasi tidak dihapus.

## Perintah individual

```bash
docker compose --profile test build api-test web-check
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps web-check npm run lint
docker compose --profile test run --rm --no-deps web-check npm run typecheck
docker compose --profile test run --rm --no-deps web-check npm test
```

Gunakan `npm run typecheck`: npm menjalankan binary lokal dari paket resmi `typescript`.
Jangan memakai `npx tsc` pada image runtime tanpa compiler, karena npm dapat mencoba mencari paket
bernama `tsc`, yang bukan paket compiler resmi TypeScript. Lockfile proyek memuat
`typescript@5.9.3`, `eslint@10.13.0`, dan tidak memuat `tsc`.

## Build targets

### Schema aset (Task 1B-01)

`tests/test_assets.py` menguji unit tanpa SN, relasi model, code kanonis/immutable/reserved,
SQL langsung, enum/version/FK, normalisasi dan duplikasi MAC, collision lintas unit/tipe,
soft-delete, ownership klaim, optimistic concurrency, snapshot audit/rollback/retensi,
index/JSONB, dan upgrade/downgrade yang mempertahankan seluruh baris sintetis delapan tabel lama.
`test_migrations.py` memeriksa head 0004, metadata (`alembic check`), roundtrip base/head.
`test_health.py` memeriksa penolakan schema lama dan tabel aset yang hilang.
Jalankan suite sama melalui `bash infra/check.sh --postgres`; fixture tetap hanya memakai
SQLite in-memory atau db-test/assetvision_test, tanpa port host maupun volume development.
Pembuatan audit pada tests ini eksplisit dalam transaksi, belum lewat API aset (Task 1B-02).

### Smoke katalog end-to-end (Task 1A-05)

```bash
bash infra/smoke-catalog.sh
```

Runner membangun API/test/web, menjalankan migrate-smoke/api-smoke/web-smoke, lalu
`python tests/smoke_catalog.py` melalui api-test. Seluruh request katalog melewati
HTTP Next.js proxy → FastAPI → PostgreSQL/PostGIS → private local storage; bukan mock.
Hanya akun sintetis yang dibuat langsung di DB, dengan password acak per run yang tidak dicetak.
Guard menolak host/nama DB/user selain db-test/assetvision_test/test_runner sebelum membuat akun.
Script tidak reset/hapus tabel; prefix acak memungkinkan pengulangan. Jangan jalankan bersamaan
dengan pytest PostgreSQL, karena fixture suite tersebut mereset tabel database uji.

Cakupan: anonymous/login/HttpOnly cookies/SSR gates, CRUD, duplikasi case/spasi,
model sama pada produsen lain, CSRF/stale version, filter/page/empty, lima foto dan hash
content privat, invalid/oversized upload, seluruh mutasi OFFICER/VIEWER 403, archive/history,
delete/primary promotion, logout, audit persisten tepat, serta cleanup backlog kosong.
Database db-test dan storage api-smoke memakai tmpfs; tidak me-mount volume aplikasi.
Trap menghentikan web-smoke/api-smoke/db-test saat exit. Data tmpfs hilang saat container
berhenti; akun/catalog sintetis tidak masuk ke development. API/web/db aplikasi tetap berjalan.
Ini tes HTTP full-stack dan SSR, bukan otomasi browser JavaScript. Tes DOM frontend tetap terpisah.
Smoke autentikasi Sprint 0 `tests/smoke_stack.py` tetap tersedia, membutuhkan suite PG bersih
sebelum mengulang bootstrap dengan email fixture yang sama.

Tes frontend katalog memakai `node:test`, React `act`, dan jsdom (dependensi development saja).
`npm run check` menjalankan ESLint, TypeScript, dan seluruh tes proxy/API client/form/interaksi UI.
Fetch pada tes UI dimock dengan data sintetis; tes tidak terhubung ke database development.
Suite backend PostgreSQL tetap memverifikasi otorisasi, validasi gambar, dan konkurensi API nyata.
Tes DOM tidak membuktikan layout browser atau end-to-end authenticated upload.

Untuk review visual terisolasi, `apps/web/tests/fixtures/catalog-preview.mjs` menyediakan
API sintetis read-only pada port 8000. Jalankan hanya di network Docker preview terpisah,
arahkan INTERNAL_API_URL container web preview ke fixture, dan bind preview ke loopback
port berbeda (misalnya 3002). Jangan mengganti INTERNAL_API_URL layanan development ke fixture.
Fixture menolak semua mutasi dan tidak membuka koneksi DB/storage. Hentikan container/network
preview setelah review. Fixture ini bukan seed database atau layanan autentikasi production.

| Service / target | Dependency yang dipasang | Tujuan |
|---|---|---|
| api / runtime | requirements.txt + requirements.lock | Menjalankan API |
| migrate / runtime | Sama dengan API runtime | Alembic |
| api-test / test | Runtime + requirements-dev.txt + requirements-dev.lock | pytest, httpx, Ruff |
| web-check / check | npm ci --include=dev dari package-lock.json | ESLint, TypeScript, pengujian frontend |
| web / runtime | Hasil standalone dari builder | Menjalankan Next.js |

Dockerfile memeriksa keberadaan alat pada waktu build. Backend menjalankan pip check;
frontend memverifikasi nama paket typescript serta versi binary ESLint dan tsc.
Build berhenti jika alat tidak tersedia, sehingga image pengujian yang tidak lengkap tidak diteruskan.

## Lockfiles dan package manager

Backend memakai pip. requirements.txt dan requirements-dev.txt menyatakan dependensi langsung.
requirements.lock dan requirements-dev.lock merekam versi lengkap termasuk dependensi transitif,
berdasarkan lingkungan Python 3.13 Linux yang diuji. Docker memasang manifest dan lock secara bersamaan:
ketidakcocokan versi membuat build gagal, bukan memilih versi baru diam-diam.
Lock runtime dan development harus diperbarui bersama bila versi dependensi runtime berubah.

Frontend memakai npm (packageManager npm@10.9.9), package.json, dan package-lock.json.
npm ci --include=dev memasang versi lockfile dan memastikan alat development tersedia pada tahap check/build.
Jangan menambahkan yarn.lock/pnpm-lock.yaml atau paket tsc ke proyek ini.

Untuk memperbarui snapshot Python setelah mengubah manifest, resolve dalam container Python bersih
lalu review kedua file sebelum build dan pengujian ulang:

```bash
docker run --rm -v "$PWD/apps/api:/src:ro" python:3.13-slim sh -c 'python -m pip install --quiet -r /src/requirements.txt >&2 && python -m pip freeze' > apps/api/requirements.lock
docker run --rm -v "$PWD/apps/api:/src:ro" python:3.13-slim sh -c 'python -m pip install --quiet -r /src/requirements-dev.txt >&2 && python -m pip freeze' > apps/api/requirements-dev.lock
bash infra/check.sh --postgres
```

Untuk perubahan frontend, update manifest dan package-lock.json menggunakan npm, kemudian build
dan jalankan pemeriksaan kembali. Tidak perlu menginstal npm global atau mengunduh compiler saat pemeriksaan.

## Audit volume dan pemulihan error

Audit saat perbaikan menemukan api/web tanpa bind mount atau named volume.
Satu-satunya volume aplikasi adalah postgres_data pada /var/lib/postgresql/data.
Dengan demikian error awal disebabkan pemilihan image runtime, bukan node_modules yang tertimpa.

Jika menambahkan override development, jangan mount seluruh direktori host ke /app pada image web check
tanpa menyediakan node_modules terpisah: mount dapat menyembunyikan dependensi yang terpasang di image.
Gunakan perintah pengujian di atas yang mengambil source dari build context. .dockerignore mengecualikan
node_modules, .next, .venv, dan cache agar dependensi host tidak masuk atau mengganti dependency image.

Setelah Dockerfile/dependensi berubah, build ulang dan recreate hanya aplikasi bila diperlukan:

```bash
docker compose build api migrate web
docker compose up -d --no-deps api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
```

Database harus sudah berjalan dan bermigrasi untuk perintah recreate dengan --no-deps.
Prosedur ini tidak menyentuh volume database atau membuat admin ulang.

## Hasil verifikasi final Sprint 0 — 18 Oktober 2026

Perintah yang dieksekusi pada Ubuntu WSL2:

```bash
bash -n infra/check.sh
bash infra/check.sh --postgres
docker compose build web
docker compose build api migrate
docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
git diff --check
docker compose run --rm --no-deps web-check npm audit --package-lock-only
```

| Pemeriksaan | Hasil aktual |
|---|---|
| Build api-test / web-check | Berhasil dari lockfile |
| pip check | No broken requirements found |
| pytest SQLite | 39 passed |
| pytest PostgreSQL/PostGIS | 39 passed; mencakup validasi migrasi |
| Ruff | All checks passed |
| ESLint | Exit 0; binary 10.13.0 tersedia |
| TypeScript tsc --noEmit | Exit 0; paket resmi typescript 5.9.3 |
| Frontend proxy tests | 5 passed, 0 failed |
| Production build API / migrate / web | Berhasil |
| Alembic current | 0001_sprint0 (head) |
| Alembic check database aplikasi | No new upgrade operations detected |
| Layanan db / api / web | Healthy sesudah recreate API/web |

Tidak ada error pengujian yang tersisa. Ada satu warning deprecation Starlette TestClient/httpx
pada masing-masing suite backend. Compose juga memberi peringatan container smoke lama yang
tidak termasuk konfigurasi aktif; tidak dilakukan penghapusan otomatis.

Container PostgreSQL aplikasi tetap memiliki ID yang sama dan memakai volume
assetvision-it_postgres_data. Jumlah pengguna tetap 1 sebelum dan sesudah rebuild.
Tidak ada penghapusan volume, penggantian database, atau pembuatan ulang admin.
Database uji db-test dihentikan oleh script setelah suite PostgreSQL selesai.

Berkas yang diubah pada perbaikan ini: compose.yaml, apps/api/Dockerfile,
apps/web/Dockerfile, apps/web/package.json, README.md.
Berkas yang ditambahkan: apps/api/requirements.lock, apps/api/requirements-dev.lock,
infra/check.sh, docs/TESTING.md, .gitattributes.
Manifest requirements*.txt dan package-lock.json yang sudah benar dipertahankan.

Referensi resmi: [npm ci dan include/omit](https://docs.npmjs.com/cli/commands/npm-ci/),
[Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/).

Final review menambahkan regresi untuk stabilitas CSRF/logout, penolakan token non-ASCII,
dan penghentian stream body proxy yang terlalu besar. Seluruh tes diulang pada source final.
Audit dependency kanonis npm audit --package-lock-only melaporkan 0 vulnerabilities.
Laporan penutupan dan inventaris commit tersedia di [SPRINT0_REPORT.md](SPRINT0_REPORT.md).
# Task 1B-02 — API unit fisik

`tests/test_asset_api.py` memeriksa CRUD tanpa SN, referensi model aktif/historis,
immutability code, bounded Pydantic, RBAC semua role, anon/nonaktif/logout, CSRF,
filter/search/pagination, collision dan duplikat, soft-delete, audit snapshot dan
rollback keenam jenis mutasi saat audit gagal. PostgreSQL menjalankan dua tes balapan
session independen: update/update dan update/identifier pada version induk sama,
tepat satu sukses dan satu 409. SQLite melewati tes row-lock tersebut.
Tes OpenAPI/proxy memeriksa rute/metode/version dan tidak membuka CSV/task berikutnya.

```bash
bash infra/check.sh --postgres
bash infra/smoke-catalog.sh
bash infra/smoke-assets.sh
```

Jalankan berurutan karena memakai db-test sama. Smoke aset memanfaatkan helper smoke katalog
dengan guard db-test/assetvision_test/test_runner dan akun sintetis baru. Semua mutasi domain
lewat HTTP Next.js/API; DB langsung hanya membuat akun dan memverifikasi audit persisten.
Runner menghentikan stack smoke/db-test dan mempertahankan database/storage development.
Tidak menjalankan seed delapan AP atau UI aset pada 1B-02.

## Task 1B-03 — CSV

tests/test_asset_csv.py memeriksa parser/header/quoted/BOM/row limit, validation/unknown model,
preview read-only via fingerprint semua tabel, duplikat CSV/DB, collision dan pengakuan,
commit ulang setelah perubahan DB, receipt actor/payload/role, rollback audit di tengah batch,
MAC/source/verification, hint staging, formula-safe export seluruh klaim dan filter,
stream/body/UTF-8 limits, dan migration 0004→0005→0004→0005 tanpa kehilangan domain.
Dua tes PostgreSQL memakai barrier/session terpisah: key sama menghasilkan receipt identik;
key berbeda dengan kode sama menghasilkan satu batch sukses dan satu ditolak tanpa parsial.

```bash
bash infra/check.sh --postgres
bash infra/smoke-catalog.sh
bash infra/smoke-assets.sh
bash infra/smoke-asset-csv.sh
```

Jalankan berurutan karena berbagi db-test sementara. Smoke CSV melalui Next.js/API/PG nyata,
memverifikasi preview tanpa write, commit tanpa SN, retry/key conflict, formula-safe export,
ADMIN-only/CSRF dan receipt/audit persisten. Guard helper mensyaratkan db-test/assetvision_test
sebagai test_runner. Semua domain sintetis, tidak membuat seed development atau UI task berikutnya.

## Task 2-02

`bash infra/check.sh --postgres` menjalankan SQLite, Ruff, frontend lint/typecheck/tests,
lalu PostgreSQL/PostGIS tmpfs. `bash infra/smoke-asset-locations.sh` membangun image dan
menjalankan AP-003 → Villa 1 hanya pada db-test sementara melalui Next.js/API nyata.
Runner mereset db-test saja dan berhenti setelah selesai. Jalankan serial terhadap suite
PostgreSQL/smoke lain. Tidak login/seed/place ke development untuk acceptance sintetis.

Tes test_asset_locations.py mencakup FK, null existing, initial event, lookup semua role,
CSRF/transport, archived/stale/replay/version-limit, PATCH bypass, rollback event failure,
retensi sejarah, migration preserve/downgrade guards serta race placement/metadata/arsip
PostgreSQL. Timeline, movement dan frontend lokasi menunggu Task 2-03–2-05.

## Task 2-03

Jalankan `bash infra/check.sh --postgres`, lalu smoke serial:
`bash infra/smoke-sprint1b.sh`, `bash infra/smoke-locations.sh`,
`bash infra/smoke-asset-locations.sh`, `bash infra/smoke-movements.sh`.
Runner terakhir memakai db-test tmpfs dengan guard nama/host test, membuat AP-003 dan
Villa 1/Villa 10 sintetis, menguji request OFFICER → approve ADMIN, reject/cancel,
stale/repeat conflicts, policy self-approval dan retensi event setelah archive. Tidak
menempatkan atau memindahkan aset development. Jangan menjalankan smoke dan suite PG bersamaan.

Test movements mencakup auth/role/CSRF/transport, validation, transisi terminal lengkap,
version/origin/eligibility stale, multiple PENDING, rollback keempat event, read-only GET,
constraints/FK/retensi dan migration pada seed/initial event predecessor. Race PostgreSQL
memakai dua session independen: double approve, dua request, approve vs reject/cancel,
metadata serta archive tujuan. SQLite hanya melewatkan tes PostgreSQL-only. Tidak ada
klaim pengujian UI movement. Pengujian timeline/observasi dilanjutkan pada 2-04 di bawah.

## Task 2-04

Jalankan `bash infra/check.sh --postgres`, lalu serial `bash infra/smoke-sprint1b.sh`,
`bash infra/smoke-locations.sh`, `bash infra/smoke-asset-locations.sh`,
`bash infra/smoke-movements.sh` dan `bash infra/smoke-observations.sh`.
Semua menggunakan db-test/assetvision_test tmpfs; jangan jalankan suite PostgreSQL dan smoke
bersamaan. Runner observasi memakai AP-003/Villa 1/Villa 10 sintetis lewat Next.js/API,
membuktikan conflict setelah approval, tidak auto-revert, review/unknown evidence, timeline
aktor/waktu/snapshot, archive retention serta RBAC/logout tanpa mutasi development.

test_observations.py mencakup body/query validation, auth/CSRF semua role, paired version,
UTC/offset/backdating, latest/stale/match/conflict, ACK/DISMISSED, unlinked/unplaced/archived,
read-only history/inbox/status/timeline, legacy metadata order dan cross-source UUID ties,
rollback audit create/review, direct SQL immutability/constraints, migration preserve dan
downgrade guard. Race PostgreSQL: observation vs approval, double review dan observation vs
archive. SQLite melewatkan tes lock PostgreSQL-only. Proxy diuji method/size/forwarding.
UI/UAT Task 2-05 belum diuji atau dimulai.

## Task 2-05 — Frontend & UAT

`tests/locations-ui.test.tsx` menjalankan React + jsdom: traversal/ancestor, role read-only,
create/parent/arsip/version, draft tetap setelah 409, canonical CSRF payload, session expiry,
placement ADMIN, request OFFICER tanpa optimistic move, observasi/timezone, unknown save
blocking, inbox/current/history/stale approval, cancel ownership, ACK semantics, read filters,
double-submit dan failure-closed preview. Tes existing katalog/registry tetap dijalankan.

Jalankan `bash infra/check.sh --postgres`, kemudian serial seluruh runner smoke predecessor
dan `bash infra/smoke-location-ui.sh`. Runner baru memeriksa redirect anonim, SSR role gates,
navigasi lokasi/inbox, fixture sintetis unplaced dan logout lewat Next.js/API/PostgreSQL nyata.
Tidak menjalankan dua suite/smoke bersamaan pada db-test yang sama.

Untuk UAT browser, `bash infra/smoke-location-ui.sh --uat` menyiapkan ulang db-test saja dan
meninggalkan stack test pada localhost:3002. Path direktori /tmp acak dicetak; session.json
berisi akun test acak dan UUID fixture dengan permission 0600, direktorinya 0700. File ini
bukan data development, tidak dicetak oleh runner atau dimasukkan Git. Setelah selesai:
`docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test stop web-smoke api-smoke db-test`.
Jangan menjalankan suite PG/smoke lain sampai UAT selesai. Daftar UAT dan hasil aktual ada di
sprints/SPRINT_2_UAT.md dan laporan 2-05. Pemeriksaan browser memakai viewport desktop dan
390×844, bukan klaim lintas browser/perangkat fisik atau audit aksesibilitas penuh.


## Task 3-01 — Evaluation harness offline

`bash infra/check-recognition-eval.sh` membangun image CPU terpisah dan menjalankan unittest
manifest/metrics tanpa jaringan, DB, credential atau volume aplikasi. Test mencakup split,
capture/hash/visual leakage, path escape/symlink, batas gambar, provenance, L2/ranking/tie,
calibration/denominator unknown, test-set independence, synthetic NO_GO dan real profile gate.
Ruff memakai konfigurasi API existing terhadap tools; tidak menambah dependency runtime API.

`bash infra/benchmark-recognition.sh DATASET_ROOT NEW_REPORT_DIR` menjalankan dua encoder
serial dengan threshold calibration-only. Dataset/prediksi privat disimpan di path ignored;
profil satu model tanpa unknown tidak menghasilkan accuracy/threshold. Prosedur dan batas
interpretasi ada di RECOGNITION_EVALUATION.md, hasil aktual di sprints/SPRINT_3_01_REPORT.md.


## Task 3-02 — Embedding generations

Tes test_recognition_index.py mencakup generation/CAS/audit atomik, fail-closed stale source/
head/spec/vector, model-level max cosine/tie/top-k, calibration provenance/unknown gate,
role/revocation, rollback storage/encoder/audit, SQL immutability/FK photo delete compatibility,
migration preservation/guard/roundtrip serta concurrent PostgreSQL rebuilds. Tes API existing
juga memverifikasi readiness head0010/tabel baru serta login/role regression. Tidak ada route
recognition baru untuk diklaim API/UI acceptance.

`bash infra/check.sh --postgres` menjalankan unit/API/lint/type/frontend dan PostgreSQL/PostGIS.
Tes CPU default di-skip bila torch tidak diinstal. `bash infra/check-recognition-index.sh`
memakai image opsional dengan weights pinned, generated images, SQLite terisolasi, network
none dan filesystem read-only; menguji dua adapter nyata, checksum/no download dan CLI nyata
status/rebuild/query/stale409. Tidak mount database/storage development. Jalankan smoke
existing secara serial setelah suite PG selesai karena memakai db-test tmpfs yang sama.
Hasil aktual dan preservasi: sprints/SPRINT_3_02_REPORT.md. Tidak menyatakan accuracy perangkat
atau kalibrasi produksi dari fixture integration/self-match.

## Task 3-03 — OCR

`tests/test_ocr.py` menguji parsing/normalisasi, raw versus correction, fallback, validasi
image/text/output dan hard timeout child. `bash infra/check-ocr.sh` membangun image CPU
opsional dan menjalankan `test_ocr_cpu.py` dengan weights nyata, network none, read-only,
CPU2/mem2GiB dan label generated. Empat tes CPU di-skip pada image API default.
Regresi penuh: `bash infra/check.sh --postgres`; semua DB test tetap terisolasi.
Angka aktual, iterasi dan preservasi ada di sprints/SPRINT_3_03_REPORT.md; detail di OCR.md.


## Task 3-04

`tests/test_evidence_fusion.py` menguji aturan dengan snapshot sintetis, tanpa DB/inference.
Jalankan melalui api-test atau full `bash infra/check.sh --postgres`. Regresi tetap mencakup
migrasi/auth/RBAC/API dan lint/TypeScript/frontend. Tidak ada klaim accuracy perangkat nyata.


## Task 3-05

`tests/test_surveys.py` menguji upload/RBAC/CSRF/ownership, raw/manual, idempotency, review
policy/stale/conflict/immutability/audit rollback dan satu pemenang race PG. Frontend jsdom
recognition/proxy tests memeriksa role, upload/unknown, koreksi, explicit checked review dan
preservasi draft. `bash infra/smoke-recognition.sh` memeriksa proxy/API/SSR/DB sintetis nyata;
jangan bersamaan writer PostgreSQL test lain. CPU6encoder/5OCR di image opsional networknone.
Laporan aktual di sprints/SPRINT_3_05_REPORT.md; tidak memulai evaluasi Task3-06.


Task3-06 menambahkan sembilan skenario API delapan AP identik pada test_recognition_e2e.py
dan runner `bash infra/evaluate-recognition.sh NEW_REPORT_FILE` untuk HTTP/proxy/PostGIS serta
profil cgroup terisolasi. Lihat [protokol](RECOGNITION_END_TO_END.md) untuk injection boundary
sintetis, batas latency/RSS dan gate dataset nyata. Jalankan serial dengan writer db-test lain.
