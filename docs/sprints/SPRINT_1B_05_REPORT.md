# Sprint 1B-05 — Hardening, audit, regression dan seed sintetis

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, suite penuh, smoke gabungan, seed development/replay dan preservasi selesai.
Scope hanya penutupan Sprint 1B. Sprint berikutnya tidak dimulai; perubahan task ini belum commit/push.

## Review Task 1B-04

Working tree awal bersih pada main, commit 320c4c0 (`feat: add Sprint 1B asset registry frontend`).
Laporan 1B-04 yang menyebut belum commit adalah catatan saat task itu selesai; sudah di-commit.
AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, spesifikasi Sprint 1B, laporan 1B-04,
API/CSV/audit/auth, migration 0001–0005, frontend/proxy, tests/runner/Compose dibaca/ditinjau.
Graph MCP list_projects dicoba dahulu; AssetVision belum terindeks, sehingga inspeksi lokal
menjadi fallback. Memory dipakai untuk workflow bounded task, DB uji terpisah dan preservasi;
status repository, data dan hasil pengujian diperiksa kembali langsung.

1B-04 sudah menyediakan list/detail/form unit/identifier, history, import/export UI, server
page guard dan frozen optimistic version. Audit atomik/retention, CSV replay/RBAC/CSRF sudah
ada pada predecessor; tidak dibangun ulang. Gap 1B-05: seed delapan AP belum ada, acceptance
seed/replay/preservasi belum dibuktikan, dan perlu regresi gabungan Sprint 0/1A/1B.
Review juga menemukan pembuatan UUID impor di luar try/finally, serta mutasi yang menerima
respons 200 non-JSON/null sebagai hasil sukses. Keduanya memerlukan perbaikan client terbatas.

Rencana: seed CLI atomik/non-overwrite → tes acceptance/audit/konflik/concurrency → perbaikan
error impor + guard unload → suite penuh dan enam smoke serial → runtime/seed development
dan pembandingan per-baris existing → dokumentasi hasil. Tidak menambah skema atau domain baru.

## Implementasi

### Seed delapan AP

`python -m app.seed_assets --actor-id UUID_ADMIN_AKTIF --confirm-synthetic` adalah operasi
development/test eksplisit, bukan startup/migration/API publik. APP_ENV=production ditolak;
actor wajib ADMIN existing aktif, tidak membuat akun/password/token baru.
Advisory lock PostgreSQL menserialisasi seed dan row lock melindungi actor/referensi.
Caller/CLI memakai satu transaksi untuk seluruh katalog/unit/claim/audit.

Kategori `access-point`/Access Point, manufacturer Ruijie, dan model `AP680-L` dibuat hanya
jika belum ada; katalog existing aktif dipakai persis tanpa UPDATE. Referensi archived atau
category model berbeda ditolak, tidak diaktifkan/diganti diam-diam. Environment OUTDOOR pada
model baru adalah metadata contoh sintetis, bukan hasil verifikasi spesifikasi hardware;
seed tidak mengubah environment model existing dan tidak mengisi spesifikasi produk.

| Unit contoh | Serial sintetis | MAC LAN | Hostname |
|---|---|---|---|
| AP-001 | 123456789 | 02:00:00:1B:00:01 | synthetic-ap-001.invalid |
| AP-002 | 2158763 | 02:00:00:1B:00:02 | synthetic-ap-002.invalid |
| AP-003 | SYNTH-1B-003 | 02:00:00:1B:00:03 | synthetic-ap-003.invalid |
| AP-004 | Tidak ada klaim SN | 02:00:00:1B:00:04 | synthetic-ap-004.invalid |
| AP-005 | Tidak ada klaim SN | 02:00:00:1B:00:05 | synthetic-ap-005.invalid |
| AP-006 | SYNTH-1B-006 | 02:00:00:1B:00:06 | synthetic-ap-006.invalid |
| AP-007 | SYNTH-1B-007 | 02:00:00:1B:00:07 | synthetic-ap-007.invalid |
| AP-008 | SYNTH-1B-008 | 02:00:00:1B:00:08 | synthetic-ap-008.invalid |

Notes seluruh unit/klaim `SYNTHETIC Sprint 1B demo; NOT production data`. MAC local-admin,
hostname `.invalid`, semua bukti IMPORT/UNVERIFIED. Total 8 unit, 22 klaim, 8 CREATE +
22 IDENTIFIER_ADD events dengan actor/time/before/after, dan catalog_create untuk tiap
referensi baru. Semua memakai model dan writer audit existing; ledger CSV tidak disentuh.

UUID unit deterministik + CREATE snapshot marker membedakan batch seed dari kode existing.
Kode yang ditempati data lain ditolak meskipun atributnya mirip; tidak diadopsi atau upsert.
Konflik UUID/identifier aktif, model mempunyai unit lain, atau batch parsial membatalkan semua.
Rerun batch lengkap tidak menulis atau menambah audit dan mempertahankan edit/arsip/claim
yang berubah setelah seed. Tidak ada repair/reset/delete. Perubahan membership model membuat
rerun menolak tanpa mutasi. Delapan contoh bukan batas jumlah unit pada domain normal.

### Hardening UI dan audit

- Pembuatan UUID impor dipindah ke try/finally. Browser tanpa randomUUID menampilkan pesan
  yang dapat dipahami dan form tidak terkunci; tidak mengirim commit tanpa UUID aman.
- Response sukses yang gagal dibaca sebagai objek JSON diperlakukan sebagai hasil belum
  pasti, tanpa sukses palsu atau retry create otomatis. Impor tetap memakai payload/key sama.
- beforeunload dipasang selama commit unresolved dan dilepas setelah sukses/ditolak.
  Ini peringatan best-effort, bukan persistensi request. CSV tidak disimpan ke localStorage.
- Regresi audit membuktikan keenam event dengan rantai version/snapshot/actor/waktu,
  history read-only semua role dan private/no-store/nosniff headers. Field identity/audit
  server yang dipalsukan ditolak tanpa perubahan. Exception audit tak terduga menghasilkan
  respons 500 generik/log aplikasi tanpa input sensitif, seluruh transaksi di-rollback.
- Tidak mengubah kontrak auth/RBAC/CSRF, optimistic concurrency, audit writer/trigger,
  schema/migration, dependency atau environment. Foto unit tetap opsional/belum tersedia.

## Berkas berubah

| Berkas | Perubahan |
|---|---|
| apps/api/app/seed_assets.py (baru) | CLI seed atomik, actor/production/conflict/ownership guards |
| apps/api/tests/test_seed_assets.py (baru) | Acceptance, repeat, conflicts/preservation, failure/concurrency |
| apps/api/tests/test_asset_hardening.py (baru) | Audit chain/read-only/privacy/server-owned-field regressions |
| apps/api/tests/smoke_seed_assets.py (baru) | CLI dua kali + search/claim/history/export HTTP nyata |
| apps/api/tests/smoke_asset_csv.py | Identifier fixture unik per run agar aman pada regresi gabungan |
| infra/smoke-sprint1b.sh (baru) | Runner enam smoke serial, reset hanya db-test tmpfs |
| apps/web/components/assets/csv-import.tsx | UUID error recovery dan unresolved unload listener |
| apps/web/lib/assets.ts | Sukses non-object/non-JSON tidak dianggap tersimpan |
| apps/web/tests/assets-ui.test.tsx | Recovery, invalid-success dan unload/retry tests |
| README.md | Operasi seed dan runner regression |
| docs/sprints/SPRINT_1B_ASSET_REGISTRY.md | Status/acceptance sesuai bukti, foto opsional dan batas sprint |
| docs/ARCHITECTURE.md, BUSINESS_RULES.md, DATABASE.md, API_CONTRACT.md, TESTING.md | Batas seed/audit/UI/preservasi/regresi |
| docs/sprints/SPRINT_1B_05_REPORT.md (baru) | Laporan task ini |

## Perintah aktual

Semua perintah Ubuntu dijalankan dari root project melalui PowerShell:
`wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it`.
Pembacaan file lokal/graph, status dan review dilakukan sebelum edit.

```bash
git status --short
docker compose exec -T api python -
# Fingerprint read-only per PK/hash sebelum perubahan; program melalui stdin.
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src --workdir /src \
  api-test python -m ruff format app/seed_assets.py tests/test_seed_assets.py \
  tests/test_asset_hardening.py tests/smoke_seed_assets.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_seed_assets.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_asset_hardening.py tests/test_seed_assets.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m ruff check app/seed_assets.py tests/test_seed_assets.py
docker compose --profile test build api-test web-check
docker compose --profile test run --rm --no-deps web-check npm run check
bash infra/check.sh --postgres
# Diulang setelah perbaikan satu signature >100 karakter yang menghentikan Ruff.
bash infra/check.sh --postgres
docker compose build api web
bash infra/smoke-sprint1b.sh
# Run pertama berhenti pada benturan fixture; diulang setelah fixture CSV dibuat unik.
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m ruff check .
bash infra/smoke-sprint1b.sh
docker compose up -d --no-deps --wait api
docker compose up -d --no-deps --wait web
docker compose exec -T api python -
# Fingerprint pre-seed, identik dengan kondisi awal; stdin read-only.
docker compose exec -T api python -m app.seed_assets --actor-id UUID_ADMIN_AKTIF --confirm-synthetic
# CLI di atas dijalankan lewat subprocess pada program stdin; UUID ADMIN existing unik
# dipilih secara read-only, tidak dicetak. Argumen --confirm-synthetic diberikan eksplisit.
docker compose exec -T api python -
# Fingerprint post-seed, lalu CLI sama diulang dan fingerprint akhir dibandingkan.
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python -
# Acceptance dataset dan probe HTTP read-only API/proxy.
docker compose ps -q db
docker compose ps -a
docker compose config --quiet
git diff --check
```

Run awal seed: 15 passed/1 PostgreSQL-only skipped; setelah menambah guard/CLI/hardening,
tes terarah menjadi 22 passed/1 skipped. Frontend terarah 57 passed, lint/tsc lulus.
Run penuh pertama SQLite 402 passed/7 skipped lalu Ruff menghentikan runner karena signature
103 karakter; dipisah menjadi multiline, bukan melonggarkan aturan. Satu unused import pada
iterasi lint awal diselesaikan dengan assertion marker sintetis yang memang perlu diuji.
Suite penuh run final selesai exit 0: SQLite **402 passed, 7 skipped**; PostgreSQL/PostGIS
**409 passed**; frontend **57 passed, 0 failed**; Ruff/ESLint/TypeScript/pip check lulus.
Ketujuh skip SQLite adalah tes khusus PostgreSQL existing (JSONB/lock/concurrency) serta
concurrent seed baru; semuanya berjalan dan lulus pada PostgreSQL. Suite juga mengulang
upgrade/downgrade/upgrade migration dan metadata check dengan fixture preservasi predecessor.
Build produksi API/web berhasil. Compose config dan git diff --check lulus.

Smoke gabungan pertama meluluskan Sprint 0, katalog dan CRUD aset, lalu berhenti pada
commit CSV 409: smoke CRUD dan CSV memakai MAC fixture sama, sehingga backend mendeteksi
collision yang belum diakui dengan benar. Fixture CSV diganti MAC local-admin dan SN yang
unik per run. Tidak mengubah aturan collision atau menambahkan bypass acknowledgement.
Ruff final diulang dan lulus; seluruh runner smoke kemudian diulang dari db-test baru.

## Hasil akhir

| Pemeriksaan | Hasil aktual |
|---|---|
| Backend SQLite final | **402 passed, 7 skipped** |
| Backend PostgreSQL/PostGIS final | **409 passed**, runner exit 0 |
| Frontend final | **57 passed, 0 failed**, ESLint dan tsc lulus |
| Ruff / pip check | All checks passed / No broken requirements found |
| Production API/web build | Berhasil, termasuk pemeriksaan TypeScript Next.js |
| Smoke Sprint 0 | 4 kelompok PASS: bootstrap/replay, login/proxy/CSRF/RBAC/logout |
| Smoke Sprint 1A | 6 kelompok PASS: katalog, filter/version, 5 foto privat, role/audit/cleanup |
| Smoke CRUD aset | 3 kelompok PASS: identity/version/SN/collision/soft-delete/RBAC/audit/logout |
| Smoke CSV | 2 kelompok PASS: preview/commit/replay/export/role/receipt/audit |
| Smoke UI | 3 kelompok PASS: SSR/navigation, page guards/role/history/logout |
| Smoke CLI seed | 2 kelompok PASS: exact-eight/SN/MAC, claim/audit/export/replay |
| Runner smoke gabungan final | **20 kelompok PASS**, exit 0; enam script serial |
| Development seed pertama | 8 assets, 22 identifiers, 3 catalog references baru |
| Development seed ulang | created_assets/created_identifiers/created_catalog=0, existing_assets=8 |
| Acceptance dataset development read-only | Benar: delapan unit tepat, seluruh claim/marker dan 30 events sesuai |
| Preservasi baris lama/storage | existingRowsAndFilesUnchanged=true |
| Penambahan hanya yang direncanakan | onlyExpectedSyntheticAdditions=true |
| Replay fingerprint semua tabel/file | seedReplayAllTablesAndFilesUnchanged=true |
| Alembic development current/check | 0005_asset_imports (head); No new upgrade operations detected |
| API/proxy readiness / assets/export/events anonim | 200 / seluruh endpoint terlindungi 401 |
| Runtime / DB container | API/web/DB healthy, container DB tidak berubah |
| Compose config / git diff --check | Lulus |

Ketujuh tes PostgreSQL-only termasuk dua worker seed yang independen: hasil [0,8] unit dibuat,
total tetap 8 unit dan 30 asset events. Audit failure injection pada katalog dan event aset
posisi awal/tengah/akhir membuktikan rollback lintas seluruh batch. Regresi API memverifikasi
keenam jenis event, rantai version, privasi 500, field spoofing dan history tanpa side effect.
Semua test/smoke mutasi berada di db-test tmpfs, kecuali seed development yang diminta secara
eksplisit pada task ini. Password/login smoke acak; tidak ada data nyata/foto masuk Git.
Warning Starlette/httpx dan orphan Compose existing tetap ada. Exit 143 web-smoke adalah
penghentian oleh trap runner; API-smoke/db-test berhenti dan seluruh runner final exit 0.

## Preservasi development dan penutupan

Sebelum perubahan, seluruh 14 tabel development dibaca dengan SET TRANSACTION READ ONLY,
diurutkan PK dan dibuat SHA-256 tiap baris; storage difingerprint dari path relatif/hash
bytes file. Hanya count/bool hasil dipublikasikan, tanpa dump, isi user/password/token atau
identitas ADMIN. Sampai setelah recreate API/web, fingerprint seluruh tabel/file masih identik
dengan awal. Tidak membuat ulang DB development, mengganti password/env, downgrade atau reset.

Setelah suite dan smoke final lulus, seed CLI dijalankan pada APP_ENV=development memakai
satu-satunya ADMIN existing aktif. Katalog kosong awal menerima satu kategori, manufacturer,
model; penambahan final persis assets +8, identifiers +22, asset_change_events +30,
audit_events +3, device_categories/manufacturers/device_models masing-masing +1.
Tidak ada perubahan/penambahan pada tabel lain atau storage. Seluruh PK/hash baris lama
tetap identik. Existing users=1, auth_sessions=1, spatial_ref_sys=8500 dan files=0 dipertahankan;
audit_events menjadi 8 (5 existing + 3 catalog_create sintetis). asset_import_batches tetap 0.

Seed ulang lewat CLI yang sama melaporkan created_assets=0/created_identifiers=0/
created_catalog=0/existing_assets=8. Fingerprint seluruh database/storage sesudah replay
identik dengan sesudah seed pertama: UUID, versi, waktu, klaim dan audit tidak berubah.
Verifikasi read-only terpisah memastikan unit AP-001…AP-008 berada pada satu model,
SN/klaim/normalisasi/marker sesuai definisi, dan 30 event dengan satu actor/waktu/snapshot.
Login development tidak dijalankan, sehingga tidak menambah session/auth audit.

Head/check tetap 0005, runtime healthy dan API/proxy read-only probes lulus. Container DB
development identik sebelum/sesudah; hanya db-test tmpfs dibuat ulang oleh runner test.
Migration 0001–0005, .env, dependency/lockfiles, next-env.d.ts, user data dan storage tidak diedit.
Status acceptance Sprint 1B diperbarui berdasarkan bukti. ID/asset_code tetap stabil,
location_hint tetap staging; tidak mengimplementasikan domain sprint berikutnya.
Perubahan Task 1B-05 siap review, belum di-stage/commit/push.

## Batas dan risiko

Tidak ada foto unit, lokasi aktif/current_location, movement, OCR/AI, controller integration,
cloud atau pekerjaan sprint berikutnya. location_hint tetap staging importer, tidak menjadi
lokasi authoritative. Actor UUID pada audit adalah aktor existing; CLI merupakan operasi host
yang dipercaya dan tidak menggantikan autentikasi API. DB owner/superuser tetap bisa mengubah
database di luar aplikasi; audit tidak diklaim tamper-proof terhadap owner.

Rerun seed tidak memulihkan isi contoh bila sudah diedit. Batch parsial/konflik memerlukan
review operator, tanpa auto-repair. Archive melalui UI/API bila contoh tidak diperlukan;
jangan menghapus riwayat atau mendaur ulang kode. Browser dapat mengabaikan beforeunload;
state request tetap hilang pada reload/navigation. Tetap pastikan hasil tidak pasti sebelum
batch baru, gunakan key/payload yang sama untuk retry.

Tes frontend adalah React DOM/JSDOM, smoke HTTP menguji SSR/proxy/API/PG nyata; bukan
browser E2E/pemeriksaan visual manual. Tidak mengklaim pemeriksaan tersebut dilakukan.
