# Sprint 2-04 — Timeline & observations

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, regresi penuh, smoke, migration development dan preservasi selesai.
Scope hanya Task 2-04. Task 2-05 tidak dimulai. Review akhir selesai; penutupan melalui
commit lokal atas permintaan pengguna, tanpa push.

## Review Task 2-03

Awal task: working tree bersih di main, HEAD 767c368295044b0638c2393a960140e922c12990,
tiga commit lokal di atas origin/main. Laporan 2-03, spesifikasi Sprint 2, AGENTS.md, README,
ARCHITECTURE, BUSINESS_RULES, migration, model/service/routes, auth/CSRF/proxy dan fixture
pengujian dibaca sebelum perubahan. Discovery MCP graph dicoba lebih dahulu; assetvision-it
belum terindeks sehingga dilanjutkan inspeksi sumber lokal. Memori hanya membantu batas
scope dan workflow WSL; keadaan Git/data diverifikasi langsung.

2-03 telah menyediakan movement request/approve/reject/cancel, row lock/version, hierarchy
lock, event atomik dan history immutable. Review akhir/commit predecessor menyatakan SQLite
550 passed/19 skipped, PostgreSQL 569 passed, frontend 60 passed dan smoke 27 kelompok.
Angka predecessor berasal dari laporan sebelumnya, bukan hasil ulang Task 2-04. Tidak ada
penghalang untuk melanjutkan; seluruh suite predecessor ikut regresi task ini.

Gap 2-04: belum ada timeline terpadu, tabel/API observasi, review dan proyeksi konflik.
Rencana: fingerprint read-only → additive migration → evidence/review/timeline/status →
tes domain/RBAC/rollback/race → regresi/build/smoke → migrate development → bandingkan
fingerprint → laporan. UI/UAT, floorplan, AI/OCR dan task berikutnya tidak dikerjakan.

## Implementasi dan keputusan

- location_observations menyimpan asset opsional, observed location/actor/time, recorded time,
  note, official location/version snapshot, comparison, snapshot_json, review dan version.
  Lokasi resmi dari aset terkunci, tidak dipercaya dari input client. Input linked memerlukan
  asset_id dan asset_version; unlinked mendukung unknown device tanpa membuat aset palsu.
- OFFICER/ADMIN create. Waktu observasi boleh backdated, wajib timezone-aware bila dikirim,
  dinormalisasi UTC dan tidak boleh future. recorded_at/actor server-owned. Note/reason
  canonical nonblank maksimal 2000 karakter; field/query ekstra ditolak.
- Snapshot/comparison UNLINKED/UNPLACED/MATCH/LOCATION_CONFLICT immutable mencatat konteks saat
  recording. Aset archived/unplaced boleh menerima bukti, observed location harus aktif lokal.
  Create maupun review tidak mengubah kolom apa pun pada aset, version atau waktu verifikasi.
- ADMIN review PENDING → ACKNOWLEDGED/DISMISSED sekali, dengan version/reason; terminal final.
  ACK tidak menghapus conflict. DISMISS mengecualikan bukti dari proyeksi aktif, sejarah tetap.
  Koreksi melalui observasi baru, tanpa edit/delete/relink evidence.
- Lock create hierarchy → asset, review hierarchy → observation → asset, mengikuti pola
  predecessor. Approval/metadata/archive bersamaan tidak menghasilkan snapshot campuran.
  Event dan evidence/keputusan atomik; injected failure me-rollback seluruh transaksi.
- Linked LOCATION_OBSERVED/LOCATION_OBSERVATION_REVIEWED memakai asset_events existing dengan
  actor, occurrence/recording timestamp, UUID correlation dan payload lengkap. Unlinked memakai
  AuditEvent existing (create/review), karena asset_events mensyaratkan asset_id non-null.
- Location-status satu SELECT mengembalikan asset/latest evidence konsisten. Latest memilih
  non-dismissed berdasarkan observed_at, recorded_at, id DESC. Jika lokasi resmi null:
  UNPLACED; tanpa bukti: NO_OBSERVATION; bukti sebelum location_verified_at: STALE_OBSERVATION;
  selain itu MATCH atau LOCATION_CONFLICT. Hanya status terakhir memberi location_conflict=true.
  Bukti lama yang baru diinput tidak auto-revert movement yang lebih baru.
- Timeline UNION ALL read-only asset_change_events (METADATA) dan asset_events (LOCATION).
  Metadata lama memakai recorded_at untuk occurrence, correlation null, payload before/after;
  tidak backfill/duplikasi atau mengubah timestamp precision existing. Source+id membedakan
  UUID yang sama. Sorting occurrence/recording/source/id DESC; bounded payload fetch per source.
- DB checks/guards PostgreSQL dan SQLite mempertahankan evidence, review state/version dan
  melarang DELETE. Append-only guards kedua sumber event existing tetap dipakai. SQL owner
  tetap wajib memakai aplikasi untuk RBAC/atomic audit; tidak mengklaim proteksi superuser.
- API/proxy reuse sesi/Origin/CSRF, bounded JSON 16 KiB, pagination default20/max100, no-store.
  Tidak ada write timeline bebas atau PATCH/delete evidence. Tidak menambah dependency/service.

## API

| Method | Route /api/v1 | Role |
|---|---|---|
| GET | /assets/{id}/timeline | Semua role authenticated |
| GET | /assets/{id}/location-status | Semua role authenticated |
| GET | /assets/{id}/location-observations | Semua role authenticated |
| POST | /location-observations | OFFICER/ADMIN |
| GET | /location-observations | ADMIN inbox |
| GET | /location-observations/{id} | ADMIN detail |
| POST | /location-observations/{id}/review | ADMIN |

Create 201; review/read 200; auth/role 401/403, unknown asset/observation 404, stale/replay/
archived observed location 409, input/unknown location 422, body 413/non-JSON415. History/inbox
filter comparison/review; inbox asset_id atau unlinked_only. Timeline filter source/event_type.
Offset/count bukan snapshot lintas request saat event baru masuk. Kontrak lengkap di
API_CONTRACT.md; tidak ada klaim frontend visual atau UAT Task 2-05.

## Perubahan file

| File | Perubahan |
|---|---|
| apps/api/app/observations.py | Model, enum, FK/check/index evidence/review |
| apps/api/migrations/versions/0009_observations.py | DDL additive, SQLite/PG guard dan safe downgrade |
| apps/api/app/observation_schemas.py | Input/output/query/status strict |
| apps/api/app/observation_service.py | Atomic create/review/event, latest location status |
| apps/api/app/observation_routes.py | Domain API dan RBAC |
| apps/api/app/timeline.py | Read-only projection/filter/pagination dua sumber |
| apps/api/app/main.py, models.py, routes.py, openapi.py | Registrasi/router/readiness/kontrak |
| apps/api/tests/test_observations.py | Domain/API/SQL/migration/rollback/race tests |
| apps/api/tests/test_migrations.py, test_health.py, test_asset_csv.py | Head/readiness regresi |
| apps/api/tests/smoke_observations.py, infra/smoke-observations.sh | Acceptance HTTP terisolasi |
| apps/web/lib/proxy.ts, tests/proxy.test.ts | Explicit route/method forwarding dan tes |
| README.md, docs/API_CONTRACT.md, ARCHITECTURE.md, BUSINESS_RULES.md | Kontrak dan semantik |
| docs/DATABASE.md, TESTING.md | Migration dan prosedur pengujian |
| docs/sprints/SPRINT_2_LOCATION_MOVEMENT.md, SPRINT_2_04_REPORT.md | Status bounded dan laporan |

## Migration dan preservasi

0009_observations hanya membuat tabel/index/trigger/function baru kosong. Tidak mengubah
migration 0001–0008, skema/data tabel existing, hint CSV atau lokasi aset. Downgrade populated
menolak sebelum DROP, termasuk dismissed; roundtrip kosong hanya diuji pada DB test.
Fingerprint awal semua kolom/baris tabel dan bytes storage direkam read-only di /tmp WSL,
bukan Git; revision Alembic satu-satunya pengecualian yang direncanakan.

Development berhasil upgrade 0008 → **0009_observations (head)**; `alembic check`:
**No new upgrade operations detected**. API/web diperbarui dan healthy, DB container/volume
tetap. Fingerprint akhir: existingTablesUnchanged=true, changedExistingTables=[],
storageUnchanged=true, dbContainerUnchanged=true, newTables=[location_observations],
newObservationCount=0. Semua kolom/baris existing identik kecuali revision Alembic.

Counts tetap: users=1, auth_sessions=1, audit_events=8, assets=8, asset_identifiers=22,
asset_change_events=30, device_categories/manufacturers/device_models masing-masing=1,
spatial_ref_sys=8500. locations, asset_events, asset_movements, asset_import_batches,
device_reference_images, storage_cleanup_jobs dan files storage tetap 0. Tidak login,
bootstrap/seed, place/move/observe/review pada development. Tidak reset/downgrade DB,
mengganti environment/password atau memetakan hint. Tidak memasukkan data nyata/foto/secret
ke Git. Migration 0001–0008, dependency/lockfiles dan next-env.d.ts tidak diubah.

Probe read-only API dan proxy: ready 200; assets/observation inbox/history/status/timeline
anonim 401. OpenAPI mendaftarkan enam route baru, timeline/status GET-only; AssetCreate/Patch
tetap tidak menerima current_location_id. Tidak mengubah sesi existing melalui probe.

## Pengujian aktual

Targeted: SQLite 68 passed/3 skipped (PostgreSQL-only); PostgreSQL 199 passed, tanpa skip.
Target migration/readiness awal 25 passed. Tes baru mencakup semua role/anon/CSRF,
transport/input/query, UTC/offset/backdating, latest/stale/conflict/match, terminal review,
unlinked/unplaced/archived, read-only GET, snapshot retention, atomic rollback linked/unlinked,
SQL immutability/constraints, upgrade populated predecessor dan downgrade guard. Tiga race
PostgreSQL memakai dua session independen: observation vs approve, double review, vs archive.

Iterasi awal SQLite menemukan asumsi tes urutan metadata berdasarkan urutan panggilan:
timestamp metadata legacy SQLite presisi detik sedangkan event baru mikrodetik. Tes diperbaiki
agar memeriksa urutan berdasarkan timestamp tersimpan dan tie-breaker, tanpa mengubah timestamp
lama. Normalisasi offset UTC sebelum persistence dan saat membandingkan naive SQLite juga
diverifikasi. Ruff menemukan tiga baris smoke panjang; string dibagi sebelum regresi penuh.

Hasil final yang sudah tersedia: SQLite **617 passed, 22 skipped** (470.39 detik),
Ruff **All checks passed**, pip check **No broken requirements found**, frontend lint +
TypeScript **lulus**, automated frontend **61 passed, 0 failed/skipped**. Build produksi
`docker compose build api web migrate` **exit 0** (termasuk kompilasi dan TypeScript Next.js).

PostgreSQL/PostGIS **639 passed, 0 skipped** (538.89 detik); runner penuh exit 0.
Seluruh 22 skip SQLite berjalan di PostgreSQL, termasuk tiga race observasi baru.

Smoke HTTP serial exit 0: observations **3**, Sprint 0/1A/1B **20**, hierarchy **2**,
initial placement **2**, movement **3** kelompok PASS; total **30**. Smoke baru membuktikan
AP-003 sintetis resmi di Villa 10 setelah approval, observasi Villa 1 menghasilkan conflict
namun master/version tetap, ACK tidak menghapus conflict, bukti baru matching menghasilkan
MATCH, unlinked dicatat/review tanpa asset palsu. Timeline berisi 7 item (1 metadata +
6 event lokasi), correlation unik, actor/time/snapshot persisten, tanpa kehilangan sejarah
setelah kedua lokasi diarsipkan. Logout menolak akses. Runner menghentikan seluruh stack
test. Regresi predecessor mencakup bootstrap/auth/CSRF, katalog/foto privat, registry/CSV/UI
existing/seed sintetis, hierarchy/cycle/retensi, placement dan movement/self-approval.

Fingerprint diulang sesudah seluruh smoke ke /tmp/av-20261019-2-04-final.json dan identik
byte dengan fingerprint pasca-migration. Pemeriksaan akhir `git diff --check` bersih,
index kosong dan API/web/db healthy. DB internal tanpa port host; API/web tetap loopback.

## Perintah yang dijalankan

Perintah berikut dari Ubuntu WSL2; runtime production tidak dipakai untuk menjalankan pytest.

```bash
git status --short --branch
git log -1 --format=fuller --stat
docker compose exec -T api python - < /tmp/av-20261019-2-04-fingerprint.py
# Output hash awal/akhir diarahkan ke /tmp/av-20261019-2-04-{before,after}.json.
# Targeted dengan source API bind read-only, --workdir /src, api-test:
python -m pytest -q tests/test_observations.py tests/test_migrations.py --tb=short -x
python -m pytest -q tests/test_observations.py tests/test_migrations.py tests/test_movements.py tests/test_asset_locations.py tests/test_health.py --tb=short -x
python -m ruff check .
docker compose build api web migrate
bash infra/check.sh --postgres
bash infra/smoke-observations.sh
bash infra/smoke-sprint1b.sh
bash infra/smoke-locations.sh
bash infra/smoke-asset-locations.sh
bash infra/smoke-movements.sh
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
python3 /tmp/av-20261019-2-04-compare.py
python3 /tmp/av-20261019-2-04-probe.py
docker compose exec -T api python - < /tmp/av-20261019-2-04-fingerprint.py > /tmp/av-20261019-2-04-final.json
cmp /tmp/av-20261019-2-04-after.json /tmp/av-20261019-2-04-final.json
docker compose config --quiet
bash -n infra/smoke-observations.sh
docker compose ps
git diff --check
git status --short --branch
git diff --cached --stat
```

Semua mutasi tes di db-test/assetvision_test tmpfs dengan guard host/database/user test,
terpisah dari development dan serial terhadap suite PostgreSQL/smoke lain. Migrasi development
dilakukan setelah regresi penuh dan smoke baru 2-04 lulus, sementara smoke predecessor
berjalan pada database terpisah; tidak menjalankan dua writer test di db-test bersamaan.
Log lokal /tmp
berisi hasil, bukan data master atau secret; tidak dimasukkan Git. Warning existing
Starlette/httpx dan Compose orphan dicatat, tanpa mengubah dependency di luar scope.

## Batas dan tindak lanjut

Timeline/status/history API siap untuk konsumsi Task 2-05 berikutnya hanya setelah diminta.
UI conflict badge/tree/inbox/timeline serta UAT visual belum dikerjakan. Tidak ada recognition,
GPS identity inference, auto-link unknown, backfill hint, penghapusan evidence atau auto-revert.
Global hierarchy lock mengikuti skala pilot lokal <500 aset. Pagination offset tidak menjamin
snapshot lintas request. Tidak ada benchmark beban atau klaim audit security/dependency baru.
Pada akhir implementasi awal, seluruh 26 berkas perubahan masih unstaged dan belum commit/push.
Tidak ada langkah manual wajib tersisa untuk implementasi Task 2-04. Penutupan lokal dicatat
di bawah; Task 2-05 hanya dapat dimulai atas permintaan berikutnya.


## Review akhir dan commit lokal

Atas permintaan pengguna, diff seluruh 26 berkas tracked/baru ditinjau sebelum staging.
Tidak ditemukan temuan penghalang commit. Review mencakup migration additive/constraint/FK/
guard retention/downgrade, evidence immutable dan keputusan terminal, snapshot/version/lock
order, actor/time, transaksi dan rollback audit linked/unlinked, latest/stale/conflict,
timeline read-only/dua sumber/tie-breaker, RBAC/CSRF/body/query limits, proxy method allowlist,
coverage tes serta konsistensi dokumentasi dan batas Task 2-05.

Log verifikasi dibaca ulang: SQLite 617 passed/22 skipped, PostgreSQL 639 passed, Ruff/pip/
frontend lint/typecheck lulus, frontend 61 passed, build produksi sukses dan smoke 30 kelompok
PASS (3+20+2+2+3). Suite tidak dijalankan ulang pada penutupan karena tidak ada perubahan kode
setelah verifikasi. Perbandingan byte/hash memastikan seluruh 86 berkas Python app/migrations/
tests identik dengan image api-test yang diuji; lib/proxy.ts, tests/proxy.test.ts, package.json
dan package-lock.json juga identik dengan web-check. Hanya laporan ini diperbarui saat review.

Fingerprint read-only diulang ke /tmp/av-20261019-2-04-review.json. `cmp` dengan fingerprint
akhir implementasi exit 0: semua data/storage tetap identik. Tidak login/seed/place/move/
observe/review atau migrate ulang development. Alembic current tetap 0009_observations (head),
API/web/db healthy dan DB tidak dipublikasikan ke host. Migration lama, environment, dependency/
lockfiles dan next-env.d.ts tidak berubah.

Staging menggunakan daftar eksplisit 26 berkas Task 2-04 pada tabel perubahan, tanpa
`git add .`, data/foto nyata, dump atau secret. Pemeriksaan `git diff --check`,
`git diff --cached --check` serta nama/stat staged ditinjau sebelum commit lokal:
`git commit -m "feat: implement Sprint 2-04 timeline and observations"`.
Identitas commit dan keadaan akhir diperiksa dengan `git log -1 --format=fuller --stat`
dan `git status --short --branch`. Tidak menjalankan push dan tidak memulai Task 2-05.
