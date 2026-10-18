# Sprint 1A-05 — Hardening dan smoke end-to-end

Tanggal: 18 Oktober 2026 (Asia/Makassar).
Status: implementasi dan verifikasi selesai; menunggu review/approval.
Berhenti pada Task 1A-05. Sprint berikutnya belum dimulai. Belum commit/push.

## Review 1A-04 dan keadaan awal

AGENTS.md, spesifikasi Sprint 1A, laporan 1A-04, README, arsitektur/aturan bisnis,
kontrak API/database, migration existing, backend/frontend/test/Compose diperiksa.
Graph MCP dicoba terlebih dahulu: assetvision-it belum terindeks. Inspeksi memakai file lokal;
tidak mengulang indexing/export kode yang ditolak pada task sebelumnya.
Hasil 1A-04 tidak memiliki masalah blocking. Gap verifikasi yang ditutup pada task ini adalah
smoke katalog melalui stack HTTP asli dan browser, di samping mock DOM yang sudah tersedia.

Working tree awal memuat pekerjaan 1A-01 sampai 1A-04 belum di-commit; dipertahankan.
API/web/db development sehat, revision 0003_image_cleanup (head), Alembic check sesuai model.
Tidak ada kebutuhan migration baru atau perubahan model/schema/domain invariant.

## Hasil hardening

**Audit:** implementasi transaksional existing dipertahankan dan diverifikasi lebih ketat.
Tes baru memastikan actor, timestamp, table/id/version, jumlah event tepat, serta tidak ada
event sukses untuk duplicate/invalid/stale/unauthorized writes. Fault injection memastikan
update/archive rollback bila audit gagal; regresi create/upload/delete existing tetap lulus.
Archive berulang pada version terbaru tidak membuat audit tambahan. PATCH is_active tetap
catalog_update, sedangkan endpoint archive memakai catalog_archive.

**Pagination:** ketiga list diperiksa pada seluruh halaman, pengulangan request, batas page/page_size,
hasil kosong, halaman jauh melewati akhir, total/total_pages, UUID tie-break, dan tidak ada duplikasi
karena beberapa alias cocok pada satu model. Urutan/filter existing tidak diubah.
Batas offset serta sifat non-snapshot saat data berubah bersamaan ditulis eksplisit.

**OpenAPI:** dependency APIKeyCookie mendeklarasikan SessionCookie untuk av_access, dengan
auto_error=False agar validasi JWT/sesi dan status 401 existing tetap berlaku. Schema menambahkan
header Origin/X-CSRF-Token untuk mutasi, penjelasan RBAC/version, batas multipart version,
content JPEG/PNG/WebP binary, dan X-Model-Version pada delete 204 tanpa body.
Tes memeriksa public/protected operations, security scheme, headers, query bounds, image fields,
serta ketiadaan storage_key/path/password_hash pada output foto. Kontrak live development diperiksa.

**Proxy:** error yang dibuat lokal (400/404/405/413/503) kini konsisten memakai Cache-Control:
no-store dan X-Content-Type-Options: nosniff, termasuk stream rusak/oversize dan API unavailable.
Response error tetap {detail: string}. Tidak memperluas allowlist atau mengubah RBAC.

**Smoke:** menambah script HTTP full-stack yang repeatable dengan nama/akun acak per run.
Guard mewajibkan PostgreSQL db-test/assetvision_test sebagai test_runner sebelum fixture akun dibuat.
Seluruh mutasi katalog melewati Next.js proxy → FastAPI → PostgreSQL/PostGIS → private local storage.
Hanya akun sintetis dibuat langsung di DB; password acak tidak dicetak oleh script.
Storage api-smoke ditaruh di tmpfs uid 10001, terpisah dari volume reference_images development.
Web smoke memiliki healthcheck; runner menunggu healthy dan menghentikan layanan uji saat exit/gagal.
Tidak ada reset/delete tabel oleh script smoke katalog. Suite pytest PG sendiri tetap mereset DB uji.

## Berkas pada Task 1A-05

| Berkas | Perubahan |
|---|---|
| apps/api/app/dependencies.py | Cookie security declaration, validasi sesi existing dipertahankan |
| apps/api/app/openapi.py (baru) | Schema CSRF/Origin/RBAC/version/pagination |
| apps/api/app/main.py | Registrasi generator OpenAPI |
| apps/api/app/image_routes.py | Kontrak multipart/version, binary content, header delete |
| apps/api/tests/test_catalog_api.py | 8 kasus parametrik audit/rollback/pagination baru |
| apps/api/tests/test_openapi.py (baru) | Kontrak security/query/multipart/binary/privacy |
| apps/api/tests/smoke_catalog.py (baru) | Smoke HTTP full-stack katalog dan audit persisten |
| apps/web/lib/proxy.ts | Header privasi untuk error lokal |
| apps/web/tests/proxy.test.ts | Satu tes mencakup lima jenis error lokal |
| compose.smoke.yaml | Storage tmpfs dan web healthcheck |
| infra/smoke-catalog.sh (baru) | Build/start/wait/run/stop smoke terisolasi |
| README.md | Status fitur dan perintah smoke |
| docs/API_CONTRACT.md | OpenAPI aktual, headers, UI tersedia, pagination semantics |
| docs/ARCHITECTURE.md | Deklarasi cookie/security OpenAPI |
| docs/BUSINESS_RULES.md | RBAC/audit/status dan batas audit |
| docs/DATABASE.md | Audit existing, tidak ada migrasi baru, isolasi smoke |
| docs/TESTING.md | Cara menjalankan, cakupan, guards, cleanup dan batas smoke |
| docs/sprints/SPRINT_1A_05_REPORT.md (baru) | Laporan ini |

File task sebelumnya yang terlihat dalam git diff bukan perubahan baru task ini.
Tidak menambah paket runtime/development, secret, akun development, dump, atau foto perusahaan.
Gambar browser sintetis dan screenshot berada di folder visualizations lokal, bukan Git.

## Pengujian dan perintah aktual

Perintah dijalankan dari root repo Ubuntu WSL2 melalui PowerShell/wsl:

```bash
git status --short
docker compose ps
docker compose exec -T api alembic current
docker compose exec -T api alembic check

# Format/check saat iterasi: image test existing, mount source API khusus.
docker compose --profile test run --rm --no-deps --user 1000:1000 \
  -v "$PWD/apps/api:/src" --workdir /src api-test python -m ruff format \
  app/openapi.py app/dependencies.py app/main.py app/image_routes.py \
  tests/test_catalog_api.py tests/test_openapi.py tests/smoke_catalog.py
docker compose --profile test run --rm --no-deps \
  -v "$PWD/apps/api:/src:ro" --workdir /src api-test python -m ruff check .

docker compose --profile test build api-test api migrate
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
docker compose --profile test build web-check
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose build web
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose config --quiet
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test config --quiet
bash -n infra/smoke-catalog.sh
bash infra/smoke-catalog.sh

# Pengulangan pada DB uji yang sama, tanpa reset di antara kedua smoke katalog:
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test up -d --wait web-smoke
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test run --rm --no-deps api-test python tests/smoke_stack.py
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test run --rm --no-deps api-test python tests/smoke_catalog.py
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test run --rm --no-deps api-test python tests/smoke_catalog.py

# Program fixture/browser audit melalui stdin; semua guard DB uji diperiksa dahulu:
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test run --rm --no-deps -T api-test python -
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test exec -T api-smoke python -
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test stop web-smoke api-smoke db-test

docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
# Program snapshot/readiness/redirect/OpenAPI read-only melalui stdin:
docker compose exec -T api python -
git diff --check
```

Perintah mount saat iterasi memakai path absolut /home/anggiatpohan/projects/assetvision-it/apps/api
(setara $PWD/apps/api). Suite penuh memakai source dalam image yang dibangun, tanpa source override.
Build web-check/check/build web diulang setelah perubahan header proxy; hasil akhir 36 tes.
Setelah suite backend penuh, perubahan script smoke hanya memperbaiki domain email fixture login;
perilaku runtime dan tes pytest tidak berubah. Script final kemudian diuji tiga run sukses.

| Pemeriksaan | Hasil aktual |
|---|---|
| Backend SQLite | **219 passed, 2 skipped** |
| Backend PostgreSQL 16/PostGIS | **221 passed** |
| SQLite skips | Inspeksi JSONB dan concurrency row-lock khusus PostgreSQL; berjalan pada suite PG |
| Frontend final | **36 passed, 0 failed** |
| ESLint / TypeScript | Lulus / lulus |
| Ruff / pip check | All checks passed / No broken requirements found |
| Build API/api-test/migrate/web-check/web | Berhasil |
| Smoke autentikasi Sprint 0 | Lulus bootstrap/idempotensi/login invalid/CSRF/cookie/SSR/role/logout |
| Smoke katalog HTTP | **3 run sukses**, termasuk 2 berturut-turut tanpa reset DB uji |
| Browser UI dengan API/DB/storage asli | Login → kategori/produsen/model → 5 foto → edit → archive → logout lulus |
| Browser content foto | 5 img complete=true, naturalWidth=160 |
| Audit browser di PostgreSQL | login=1, catalog_create=3, reference_image_upload=5, catalog_update=1, catalog_archive=1, logout=1 |
| Model browser sesudah archive | UUID tetap, version=8, inactive, 5 referensi tetap ada |
| Storage smoke setelah seluruh run/browser | 13 metadata = 13 files; cleanup jobs=0 |
| Alembic development | 0003_image_cleanup (head), check tidak menemukan operasi baru |
| Readiness development API/web | 200 / 200 |
| Protected list/new/settings development anonim | 307 /login |
| OpenAPI live development | SessionCookie terverifikasi |
| Fingerprint seluruh tabel/file development | **Sama persis** dengan snapshot awal |
| Compose normal/smoke config, shell syntax, diff check | Lulus |

Output smoke katalog final:

```text
PASS anonymous redirects, login, cookie forwarding, authenticated SSR
PASS CRUD, duplicates, cross-manufacturer, CSRF/version, filters/pagination/empty
PASS five uploads, private content/hash, invalid/oversized rejection
PASS OFFICER/VIEWER reads, every mutation 403, SSR ADMIN gates, logout
PASS archive/history/images, idempotency, delete/primary promotion, anonymous denial
PASS persisted audit actions/actor/keys/timestamps, no false success audit, empty cleanup
```

## Bukti acceptance Sprint 1A

| Kriteria | Bukti |
|---|---|
| ADMIN membuat kategori/produsen/model | HTTP smoke dan browser UI asli |
| Duplikasi case/spasi ditolak; produsen berbeda boleh | HTTP smoke 409 / 201 dan API regression |
| Minimal lima foto upload dan dibaca kembali | HTTP smoke hash checks; browser 5 gambar termuat |
| Invalid/oversize ditolak, tanpa orphan | HTTP smoke 415/413, API failure/cleanup tests; metadata/files smoke sama |
| OFFICER/VIEWER tidak dapat mutasi | HTTP smoke semua jenis mutasi 403; API regression dan DOM role controls |
| Archive mempertahankan histori/foto | HTTP smoke, browser, audit dan metadata PostgreSQL |
| Filter/page/empty/mobile | API + DOM regression; review responsive 1A-04 tidak terdampak perubahan proxy/schema docs |
| Migration/backend/frontend checks | Suite penuh SQLite/PG, lint/typecheck/build dan live Alembic check |

Ini bukti implementasi/pengujian, bukan pengganti approval owner.

## Pelestarian data development

Sebelum perubahan dan setelah recreate hanya API/web, snapshot seluruh isi baris delapan tabel
diurutkan UUID lalu di-hash SHA-256; metadata file/hash dan revision juga dibandingkan.
Pembacaan memakai SET TRANSACTION READ ONLY. Assertion perbandingan menghasilkan true.
Tidak mencetak isi baris/password/token. Count tetap:

```text
users=1, auth_sessions=1, audit_events=5
device_categories=0, manufacturers=0, device_models=0, device_reference_images=0
storage_cleanup_jobs=0, reference files=0
revision=0003_image_cleanup
```

Tidak menjalankan login/mutasi katalog/seed/upgrade/downgrade pada database development.
Database dan volume development tidak direcreate/dihapus. API/web/db healthy setelah pemeriksaan.
Layanan smoke dan db-test dihentikan; tmpfs uji dibersihkan oleh stop. Tab browser uji ditutup.

## Masalah yang diselesaikan dan batasan

Ruff awal menemukan enam baris terlalu panjang; diperbaiki. Smoke pertama menggunakan email
fixture example.invalid yang ditolak validator EmailStr (422). Fixture diganti ke example.com;
password tetap acak, dan run final sukses. Tidak mengubah validator login untuk mengakomodasi tes.
PNG browser awal yang disalin lewat base64 gagal integrity verification meskipun dapat dibuka.
Backend menolaknya 422 tanpa menyimpan foto. Fixture dibuat ulang langsung dengan Pillow dan
lolos validate_image sebelum diunggah; lima foto kemudian berhasil melalui UI.
File chooser browser lambat, tetapi unggahan dan pemeriksaan akhirnya selesai.
Docker Hub dapat diakses; build memakai dependency lock/cache tanpa fallback runtime.

Satu warning deprecation Starlette TestClient/httpx tetap ada. Compose memperingatkan container
smoke saat konfigurasi normal tidak memuat service test; layanan tersebut dihentikan, tidak
menghapus container/volume milik pekerjaan lama otomatis. Git memberi peringatan normalisasi
CRLF pada package/proxy test files; diff --check tetap exit 0. Tidak ada tes gagal tersisa.

Offset pagination tidak menjamin snapshot saat ada concurrent insert/rename/archive, bahkan
count dan rows dapat berubah di antara query pada request yang sama. Skala awal <500 aset;
cursor/snapshot pagination belum ditambahkan. Filter UI belum disimpan ke URL (batas 1A-04).
Audit berisi referensi aksi/version, bukan diff field lengkap atau tamper-proof ledger.
Cleanup CLI masih operasional manual bila intent tertunda; tidak menambah scheduler/worker.
Browser smoke dilakukan lewat tool UI pada sesi ini; runner repeatable yang disimpan adalah
HTTP full-stack/SSR, bukan suite browser otomatis. Delete foto serta RBAC seluruh mutasi
diverifikasi di HTTP/API tests; browser manual mencakup create/upload/edit/archive/logout.
Tidak ada AI/OCR/unit aset/lokasi/pergerakan/cloud atau pekerjaan Sprint 1B.

## Langkah review

1. Review openapi.py/dependencies.py/image_routes.py dan kontrak API; cek /docs atau /openapi.json.
2. Review audit/pagination tests dan proxy error headers. Tidak perlu migrasi baru.
3. Jalankan bash infra/check.sh --postgres, kemudian bash infra/smoke-catalog.sh secara berurutan.
   Jangan arahkan TEST_DATABASE_URL ke development atau menjalankan suite PG bersamaan dengan smoke.
4. Login akun existing di localhost:3000 untuk review UI; katalog development tetap kosong.
   Gunakan stack uji terpisah untuk demonstrasi mutasi. Backup DB dan volume foto tetap bersama.
5. Review laporan ini dan berikan approval terpisah untuk pekerjaan berikutnya.
   Task 1A-05 selesai; sprint berikutnya tidak dimulai.
