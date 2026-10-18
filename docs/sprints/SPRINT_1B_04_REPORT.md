# Sprint 1B-04 — Frontend registry aset fisik

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi, pengujian, smoke, runtime lokal dan preservasi selesai; siap review.
Scope: Task 1B-04; tidak memulai hardening/seed 1B-05.
Belum commit/push perubahan task ini.

## Review Task 1B-03 dan rencana

AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, spesifikasi Sprint 1B, laporan 1B-03,
source API/CSV/auth/proxy/katalog, pola frontend/tests/Compose dan migration 0001–0005
ditinjau sebelum implementasi. Git awal bersih pada main, commit 3f1f6ed (1B-01–03).
Status belum commit di laporan predecessor adalah catatan historis; hasilnya sudah committed.
Graph MCP list_projects hanya memuat payload-cms-villa, sehingga inspeksi lokal dipakai
sebagai fallback tanpa indexing/upload repository. Memory proyek dipakai untuk pola bounded
task, pengujian terisolasi dan preservasi; semua status/test/migration diverifikasi ulang.

API predecessor sudah menyediakan unit/identifier CRUD, optimistic version, RBAC/CSRF,
CSV preview/commit/export, receipt idempotency dan audit transaksional. Gap untuk slice ini:
belum ada halaman aset/form/import, navigasi, atau endpoint baca audit untuk detail.
Rencana: gunakan pola sesi/style/resource katalog existing → daftar/form/detail/identifier
→ endpoint baca riwayat minimal → upload/preview/konfirmasi/ringkasan CSV → tests/regresi,
smoke dan fingerprint data → laporan. Tidak membangun alur lokasi atau audit writer baru.

## Hasil implementasi

- `/assets`: list Asset ID/model/status/kondisi, pencarian Asset ID/SN/MAC, filter model/status,
  pagination 15 per halaman. Mengubah filter kembali ke halaman 1. Export ADMIN menggunakan
  filter yang sudah diterapkan, semua halaman, melalui endpoint aman 1B-03.
- `/assets/new`: form ADMIN memilih model aktif katalog, status/kondisi, catatan, tanggal
  pembelian dan waktu pemasangan opsional. Waktu wajib ISO 8601 dengan zona eksplisit.
  Tidak ada field SN wajib atau placeholder. Setelah unit dibuat, ditampilkan tautan detail;
  identifier ditambah terpisah agar keberhasilan unit tidak tersembunyi jika klaim gagal.
- `/assets/{id}`: metadata, model tertaut, UUID permanen, versi, waktu, identifier, riwayat.
  Asset code disabled pada edit dan tidak masuk payload PATCH. Referensi model archived
  existing tetap dapat dipertahankan; pergantian hanya ke model aktif. Archive dikonfirmasi,
  tanpa hard-delete; pemulihan memakai pilihan status dalam form edit sesuai API existing.
- Form menyimpan base version saat mulai edit, tidak mengadopsi background version baru.
  Konflik mempertahankan isian dan memblokir penyimpanan ulang sampai data dimuat ulang.
  Kegagalan koneksi mutasi non-idempotent juga meminta pemeriksaan data terbaru, tanpa retry
  otomatis. Metadata/identifier tidak diedit bersamaan dalam detail yang sama.
- Identifier mendukung keenam tipe, raw evidence + normalized value, sumber, verifikasi,
  catatan, edit dan konfirmasi soft-delete. Payload menggunakan asset_version serta version
  klaim saat diperlukan. SN absent menampilkan informasi tidak tersedia/label rusak tanpa
  membuat klaim palsu. Collision menautkan UUID unit lain tanpa merge/overwrite.
- `GET /assets/{asset_id}/events` adalah penambahan backend minimal untuk UI: semua role
  authenticated yang dapat membaca unit, scoped per unit, pagination 1–100, snapshot
  sebelum/sesudah, actor UUID, tipe dan waktu. Sort waktu desc, versi snapshot desc sebagai
  pembeda waktu sama, lalu UUID desc. Tidak membuka email/password/session atau metode tulis.
  Audit writer/tabel/triggers/retensi existing tidak diubah. Tidak ada migration baru.
- `/assets/import`: file UTF-8 strict, preflight tidak kosong/256 KiB, informasi header,
  enum dan batas 500 baris; parser/validasi domain tetap backend. Preview memperlihatkan
  setiap row/error/collision/staging hint. File baru membatalkan preview dan acknowledgement.
  Row invalid memblokir commit; collision memerlukan checkbox eksplisit; commit dikonfirmasi.
- Commit membuat UUID satu kali, menyimpan CSV/key/flag sebagai request immutable dalam
  state halaman. Jika hasil tidak pasti, file/flag terkunci dan retry mengirim request persis
  sama. Tidak ada retry otomatis. COMMITTED menampilkan jumlah/unit tertaut; REJECTED 409
  menampilkan batch/row errors dan mewajibkan preview ulang. `location_hint` hanya staging.
- Layout server memeriksa sesi; halaman new/import memeriksa ADMIN di server. OFFICER/VIEWER
  membaca list/detail/audit tanpa kontrol mutasi/import/export. Backend tetap memegang semua
  authorization. Proxy/CSRF/cookie HttpOnly existing dipakai; token tidak masuk localStorage.
- Navigasi ditambahkan di workspace dan katalog. Style katalog dipakai ulang dengan tambahan
  kecil untuk identifier/audit/responsiveness, loading/error/empty dan keyboard focus existing.

## Berkas berubah

| Berkas / kelompok | Perubahan |
|---|---|
| apps/web/lib/assets.ts (baru) | Types, filter/payload/identifier/file validation, mutation CSRF/error |
| apps/web/components/assets/model-options.ts (baru) | Semua halaman model/produsen + historical labels |
| apps/web/components/assets/asset-list.tsx (baru) | Search/filter/page/export dan role controls |
| apps/web/components/assets/asset-form.tsx (baru) | Create/edit metadata dengan frozen version |
| apps/web/components/assets/new-asset.tsx (baru) | Create result dan tautan identifier detail |
| apps/web/components/assets/asset-detail.tsx (baru) | Metadata/edit/archive dan koordinasi refresh |
| apps/web/components/assets/identifiers.tsx (baru) | Bukti klaim, source/verification, collision, edit/soft-delete |
| apps/web/components/assets/audit.tsx (baru) | Paginated read-only snapshot history |
| apps/web/components/assets/csv-import.tsx (baru) | Upload/preview/confirm/summary/retry immutable |
| apps/web/app/assets/layout.tsx (baru) | Server auth dan role/navigation/style |
| apps/web/app/assets/page.tsx (baru) | List route |
| apps/web/app/assets/new/page.tsx (baru) | ADMIN create page guard |
| apps/web/app/assets/import/page.tsx (baru) | ADMIN import page guard |
| apps/web/app/assets/[id]/page.tsx (baru) | UUID detail route validation |
| apps/web/app/assets/loading.tsx, error.tsx, not-found.tsx (baru) | Route recovery states |
| apps/web/app/assets/assets.css (baru) | Identifier/audit/overflow presentation |
| apps/web/app/dashboard/page.tsx, app/catalog/layout.tsx | Navigasi registry |
| apps/web/lib/proxy.ts | GET-only events allowlist |
| apps/web/tests/assets-ui.test.tsx (baru) | 17 tes React DOM/JSDOM dan kontrak client |
| apps/web/tests/proxy.test.ts | Events forward dan mutation method rejection |
| apps/api/app/asset_schemas.py, asset_routes.py | Event output/query/read route |
| apps/api/tests/test_asset_api.py, test_openapi.py | History scope/role/query/snapshot/no-write/contract |
| apps/api/tests/smoke_asset_ui.py (baru) | SSR/role/history HTTP smoke terisolasi |
| infra/smoke-asset-ui.sh (baru) | Production build + isolated smoke runner/cleanup stop |
| README.md; docs/API_CONTRACT.md, ARCHITECTURE.md, BUSINESS_RULES.md, TESTING.md | Panduan dan batas UI |
| docs/sprints/SPRINT_1B_04_REPORT.md (baru) | Laporan ini |

## Perintah aktual

Seluruh perintah Ubuntu dijalankan dari root project melalui prefix PowerShell:
`wsl -d Ubuntu --cd /home/anggiatpohan/projects/assetvision-it`.

```bash
git status --short
docker compose exec -T api python -
# Fingerprint read-only seluruh tabel/storage, dikirim melalui stdin; bukan dump.
docker compose --profile test build api-test web-check
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m pytest -q tests/test_asset_api.py tests/test_openapi.py
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/src:ro --workdir /src \
  api-test python -m ruff check .
bash infra/check.sh --postgres
docker compose build api web
bash infra/smoke-asset-ui.sh
bash infra/smoke-asset-csv.sh
docker compose up -d --no-deps --wait api
docker compose up -d --no-deps --wait web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python -
# Fingerprint akhir dan HTTP probes read-only melalui stdin.
docker compose ps -q db
docker compose ps -a
docker compose config --quiet
git diff --check
```

Pemeriksaan terarah, build dan frontend check diulang selama iterasi perbaikan.
Percobaan lint source-mounted yang gagal resolve dependency memakai:
`docker compose --profile test run --rm --no-deps -v .../apps/web:/src:ro --workdir /src
web-check sh -c 'ln -s /app/node_modules /tmp/assetvision-node-modules 2>/dev/null || true;
/app/node_modules/.bin/eslint .'`. Tidak dipakai sebagai bukti lint lulus; image kemudian
dibangun ulang dan `npm run check` serta runner lengkap berhasil. Symlink hanya berada di
container sementara, tidak di workspace. Laporan hasil memakai run berhasil yang benar-benar
ditutup dengan exit 0, bukan status wrapper shell dari percobaan awal.

## Hasil yang telah diverifikasi

| Pemeriksaan | Hasil |
|---|---|
| Backend terarah setelah perbaikan | 48 passed, 2 skipped (PostgreSQL-only) |
| Backend SQLite penuh | 380 passed, 6 skipped (PostgreSQL-only) |
| Backend PostgreSQL/PostGIS penuh | 386 passed, exit 0 |
| Frontend penuh | 55 passed, 0 failed; termasuk 17 tes baru aset |
| ESLint / TypeScript / Ruff / pip check | Lulus |
| Production API/web build | Berhasil, empat route aset tersedia |
| Compose config / git diff --check | Lulus |
| Smoke halaman/role/history nyata | Tiga kelompok PASS, exit 0 |
| Smoke CSV predecessor | Dua kelompok PASS, exit 0 |
| Runtime database/API/web | Healthy; container database tidak berubah |
| Alembic development current/check | 0005_asset_imports (head); No new upgrade operations detected |
| API/proxy ready | 200 / 200 |
| API/proxy assets/export/events anonim | Semua 401 |
| Halaman assets/new/import anonim | Semua 307 ke /login |
| Preservasi seluruh tabel/storage | allTablesAndFilesUnchanged=true |

Keenam skip SQLite adalah tes khusus PostgreSQL existing (JSONB/lock/concurrency katalog,
unit dan CSV); semuanya berjalan/lulus pada suite PostgreSQL. Suite mencakup unit/API/CSV,
auth/unauthorized/CSRF, audit rollback, migration upgrade/downgrade/metadata check serta
regresi Sprint 0/1A/1B sebelumnya pada database uji, tanpa mengubah fixture ke development.
Smoke UI membuktikan redirect anonim, navigasi workspace/katalog, ADMIN SSR/create/import
page, detail/history, pembatasan page server untuk kedua role baca, write 403, dan logout.
Smoke CSV mengulang preview read-only, unit tanpa SN, commit/replay/key conflict, safe export,
ADMIN-only/CSRF, receipt dan audit persisten tanpa duplicate unit/event. Semua mutasi smoke
dan suite memakai db-test/assetvision_test/test_runner dengan storage tmpfs terisolasi.
Kedua runner menghentikan web-smoke/api-smoke/db-test setelah selesai. Exit 143 web-smoke
pada daftar container adalah penghentian oleh runner, bukan kegagalan tes.

Iterasi awal menemukan lint control-character regex, type narrowing pada tes, dua baris
smoke terlalu panjang dan urutan event timestamp sama. Semuanya diperbaiki lalu tes diulang;
tidak melonggarkan validasi/authorization. Upaya lint lewat source mount /src tidak dapat
resolve dependency ESLint, sehingga beralih ke pola image build existing. Tidak mengubah
dependency atau membuat node_modules di workspace. Warning Starlette/httpx dan orphan
container existing dicatat, tidak menjadi klaim tes gagal atau alasan menghapus volume.

## Preservasi dan runtime akhir

Sebelum pembaruan, program stdin membaca seluruh tabel development dengan
SET TRANSACTION READ ONLY, SELECT terurut, serialisasi JSON deterministik dan SHA-256.
Path relatif/hash bytes storage juga difingerprint. Hanya count/hash dicetak, tanpa dump,
isi baris, password, token atau foto. Setelah suite/smoke lulus, hanya API dan web di-recreate
dengan --no-deps --wait, tanpa restart/recreate DB, migration baru, downgrade atau reset volume.
Tidak melakukan login/bootstrap/seed/import atau mutasi domain pada development.

Program fingerprint yang sama sesudah pembaruan dibandingkan dengan hasil awal:
**allTablesAndFilesUnchanged=true**, seluruh 14 tabel termasuk alembic_version/PostGIS
dan storage file identik. Jumlah existing tetap users=1, auth_sessions=1, audit_events=5,
spatial_ref_sys=8500; seluruh tabel katalog/aset/import/cleanup kosong, file=0.
Identitas container database juga identik sebelum/sesudah. Suite migration di database uji
tetap mencakup fixture preservasi nonkosong predecessor, bukan hanya development yang kosong.

Revisi tetap 0005_asset_imports, Alembic check tanpa operasi baru. Readiness API dan proxy 200;
assets/export/events anonim 401; halaman /assets, /assets/new dan /assets/import mengarah ke
/login dengan 307. OpenAPI runtime memuat events GET. Probe final read-only, tidak membuat
sesi/audit baru. API/web/DB healthy, test services stopped. .env, dependency/lockfile,
next-env.d.ts, migration existing dan data pengguna tidak diubah.

## Batas

Foto unit opsional belum diimplementasikan; detail menautkan model yang mempunyai foto
referensi Sprint 1A, tanpa menganggapnya foto unit. Tidak ada lokasi aktif/movement/OCR/AI.
Seed delapan AP, hardening dan acceptance sprint penuh tetap Task 1B-05, belum dimulai.
Snapshot history memakai offset pagination biasa, bukan snapshot global terhadap writer lain.
Actor tampil sebagai UUID; tidak menambah endpoint pengelolaan/pencarian pengguna.

Retry CSV client bertahan selama halaman terbuka. Navigasi/reload meniadakan state request
client; pengguna harus memastikan hasil sebelum batch lain. Ledger idempotency server tetap
persisten. Tidak menyimpan CSV/sesi di localStorage atau memperkenalkan storage browser baru.
Pengujian interaksi adalah React DOM/JSDOM dengan mocked fetch; HTTP smoke menguji SSR dan
integrasi nyata, bukan browser E2E/visual manual. Tidak mengklaim pemeriksaan visual browser.
