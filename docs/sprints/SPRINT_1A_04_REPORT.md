# Sprint 1A-04 — Frontend katalog perangkat

Tanggal: 18 Oktober 2026 (Asia/Makassar).
Status: implementasi dan pemeriksaan selesai; menunggu review/approval.
Task 1A-05 belum dimulai. Belum commit/push.

## Review prasyarat

AGENTS.md, README, arsitektur/aturan bisnis, spesifikasi Sprint 1A, laporan 1A-03,
kontrak API, auth/proxy, schema/migrasi, dan pola pengujian diperiksa sebelum perubahan.
Graph MCP dicoba terlebih dahulu; proyek belum terindeks sehingga inspeksi memakai file lokal.
Tidak mengulang indexing yang ditolak pada task sebelumnya. Hasil 1A-03 tidak mempunyai
masalah blocking: schema development berada pada 0003_image_cleanup (head), Alembic check
tidak mendeteksi perubahan, regresi SQLite 210 passed/2 skipped dan PostgreSQL 212 passed.
Working tree awal berisi pekerjaan 1A-01/02/03 yang belum di-commit; semuanya dipertahankan.

Tidak mengubah API, proxy, schema, migration, volume, akun, atau data development pada task ini.
Hanya container web development yang dibangun ulang/recreate. Pengujian mutasi memakai
mock DOM atau database/files sementara pada service test.

## Hasil implementasi

- `/catalog/models`: tabel, pencarian, filter kategori/produsen/status, pagination 15 baris,
  loading, hasil kosong, error/retry, dan tautan detail.
- `/catalog/models/new`: form ADMIN dengan normalisasi nama/alias, referensi aktif,
  deskripsi/environment/status, validasi panjang/jumlah/ukuran request.
- `/catalog/models/[id]`: detail, editor, archive/restore dengan konfirmasi, spesifikasi,
  galeri privat, multi-file upload berurutan, dan delete foto dengan konfirmasi/version.
- `/catalog/settings`: pengelolaan kategori/produsen ADMIN, tambah/edit/nonaktifkan,
  validasi, pagination, serta konflik yang mempertahankan isian.
- Editor spesifikasi mendukung string/angka/boolean/null/list scalar tanpa mengharuskan
  pengguna menulis JSON. Nilai typed existing tetap dipertahankan saat roundtrip.
- OFFICER/VIEWER membaca katalog/galeri tanpa kontrol mutasi. Layout memeriksa sesi server;
  halaman tambah/pengaturan memeriksa ADMIN server. Backend tetap menegakkan RBAC per request.
- Link katalog ditambahkan ke workspace; navigasi, label form, skip link, focus style,
  native dialog, status/alert, fallback foto, dan layout responsive tersedia.

Komponen client menggunakan proxy same-origin existing dan cookie HttpOnly. Mutasi mengambil
CSRF sesi dari `/auth/session`; tidak mengekspos JWT kepada JavaScript. Foto dimuat langsung
dari content_url terautentikasi, tanpa cache Next image optimization.

Draft edit menyimpan version awal; background refresh tidak boleh memperbarui baseline draft.
409 mempertahankan isian dan memerlukan tindakan muat ulang eksplisit. Tidak ada retry otomatis
untuk POST/PATCH/DELETE. Galeri memakai model_version dari response upload berikutnya;
kegagalan parsial menampilkan jumlah foto yang sudah berhasil dan memuat ulang daftar.
Preflight foto memeriksa JPEG/PNG/WebP dan maksimal 8 MiB; validasi backend tetap authoritative.

## Berkas pada Task 1A-04

| Berkas | Perubahan |
|---|---|
| apps/web/app/catalog/layout.tsx | Auth server, role provider, shell/navigasi |
| apps/web/app/catalog/models/page.tsx | Daftar katalog |
| apps/web/app/catalog/models/new/page.tsx | Halaman tambah, gate ADMIN |
| apps/web/app/catalog/models/[id]/page.tsx | Detail dan validasi UUID |
| apps/web/app/catalog/settings/page.tsx | Halaman pengelolaan ADMIN |
| apps/web/app/catalog/loading.tsx, error.tsx, not-found.tsx | State route |
| apps/web/app/catalog/catalog.css | Styling responsive scoped |
| apps/web/components/catalog/resource.ts, options.ts | Pembacaan abortable, pagination referensi, reload |
| apps/web/components/catalog/shared.tsx | Role/context, error/state, konfirmasi/pagination |
| apps/web/components/catalog/model-list.tsx | List/filter/search/pagination |
| apps/web/components/catalog/model-form.tsx, spec-editor.tsx, new-model.tsx | Form dan editor typed |
| apps/web/components/catalog/model-detail.tsx | Detail/edit/archive/restore |
| apps/web/components/catalog/gallery.tsx | Upload/serve/delete UI dan kegagalan parsial |
| apps/web/components/catalog/master-manager.tsx | Kategori/produsen |
| apps/web/lib/catalog.ts, catalog-form.ts | Types, API client/CSRF/errors, validasi/payload |
| apps/web/tests/catalog.test.ts | 7 tes helper/client/validasi |
| apps/web/tests/catalog-ui.test.tsx | 18 tes interaksi DOM |
| apps/web/tests/fixtures/catalog-preview.mjs | API sintetis read-only khusus review visual |
| apps/web/app/dashboard/page.tsx | Link ke katalog |
| apps/web/package.json, package-lock.json | jsdom/@types development dan test TSX |
| README.md, docs/ARCHITECTURE.md, docs/API_CONTRACT.md, docs/TESTING.md | Cara akses, batas arsitektur/testing |
| docs/sprints/SPRINT_1A_04_REPORT.md | Laporan ini |

Perubahan API/proxy/Compose/migration lain yang terlihat di git status berasal dari task sebelumnya.
Tidak ada dependensi runtime baru, foto asli, credential, dump, atau seed development baru.

## Perintah yang benar-benar dijalankan

Perintah dari root repository dalam Ubuntu WSL2 (dipanggil melalui PowerShell/wsl):

```bash
git status --short
docker compose ps
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose --profile test build web-check
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose build web
docker compose up -d --no-deps --wait web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose config --quiet
git diff --check
# Program read-only count/HTTP melalui stdin, tanpa mencetak isi data atau rahasia:
docker compose exec -T api python -
```

Lockfile diperbarui melalui container Node dengan npm install --package-lock-only --ignore-scripts
untuk jsdom/@types; audit dependency menghasilkan 0 vulnerabilities. Iterasi awal memakai copy source
dari mount read-only ke image web-check agar node_modules image tetap tersedia. Pemeriksaan final
membangun ulang web-check dan menjalankan npm run check langsung pada image, tanpa source override.

Review browser memakai image web produksi yang sama, port loopback 3002 dan network preview
terpisah, diarahkan ke fixture GET-only. Tidak terhubung ke DB atau storage development.
Container preview/fixture dan network sementara dibersihkan setelah review; db-test dihentikan.

## Hasil pengujian aktual

| Pemeriksaan | Hasil |
|---|---|
| ESLint / TypeScript | Lulus / lulus |
| Frontend final | **35 passed, 0 failed** (18 DOM + 7 helper/client + 10 proxy existing) |
| Build Next.js produksi | Berhasil; empat route katalog dynamic terdaftar |
| Backend SQLite | **210 passed, 2 skipped** |
| Backend PostgreSQL/PostGIS | **212 passed** |
| Ruff / pip check | All checks passed / No broken requirements found |
| Alembic development current / check | 0003_image_cleanup (head) / No new upgrade operations detected |
| Anonim pada list/new/detail/settings development | **307 /login** untuk keempat halaman |
| Readiness API dan proxy web | **200 / 200** |
| Compose config / git diff --check | Exit 0 / exit 0 |
| Browser preview sintetis | List desktop/mobile, form baru, detail, halaman kategori/produsen diperiksa |
| Browser console preview | Tidak ada error yang terekam |

Tes DOM mencakup role controls, filter/pagination reset, loading/empty/retry, payload create,
validasi, 409 dengan draft/version tetap, background refresh saat edit, kategori/produsen,
archive cancel/confirm, sequential upload/version, partial failure yang tetap terlihat sesudah
refresh detail, preflight foto, fallback content, dan delete dengan konfirmasi/version.
Tes API backend mencakup login/RBAC, duplikasi, validasi/penyimpanan/serve/delete foto,
konkurensi PostgreSQL, archive, dan roundtrip migration pada database uji.
Skip SQLite khusus inspeksi JSONB dan row-lock concurrency PostgreSQL; keduanya berjalan di suite PG.

Pada review mobile 390 px ditemukan overflow label tabel tersembunyi. Scroller tabel diberi
position context; setelah perbaikan document scrollWidth 375 (scrollbar) pada viewport 390,
sehingga overflow dibatasi ke tabel. Form/detail juga tidak melebarkan halaman.

## Pelestarian data

Snapshot count development sebelum dan setelah pemeriksaan/recreate tetap:

```text
users=1, auth_sessions=1, audit_events=5
device_categories=0, manufacturers=0, device_models=0, device_reference_images=0
storage_cleanup_jobs=0, reference files=0
revision=0003_image_cleanup
```

Pembacaan akhir memakai transaksi READ ONLY. Tidak menjalankan upgrade/downgrade, bootstrap,
seed, login baru, upload, atau delete pada development. API/db/volume existing tidak direcreate.

## Masalah yang diselesaikan dan batasan

Update lockfile pertama gagal karena kepemilikan file; diselesaikan dengan menjalankan npm
di container sebagai root hanya untuk lockfile, tanpa chmod/chown host. Build pertama mengalami
ECONNRESET saat npm download; retry dengan lockfile sama berhasil. Tidak perlu fallback install
pada runtime. TypeScript sempat menemukan narrowing model dalam closure; diperbaiki sebelum
suite final. Probe HTTP pertama mencoba httpx yang memang tidak ada di image runtime; probe
diulang dengan urllib standar, tanpa memasang paket pada aplikasi. Tidak ada tes gagal tersisa.

Warning deprecation Starlette TestClient/httpx serta peringatan Compose tentang container smoke
lama tetap ada. Container lama tersebut tidak dihapus. Normalisasi CRLF pada package files
diperingatkan Git, tetapi diff --check exit 0.

Tes UI memakai mock fetch; review browser memakai API sintetis read-only, galeri fixture kosong.
Belum menjalankan alur browser authenticated create/upload/delete terhadap API nyata; tidak
mengklaim smoke end-to-end selesai. Integrasi mutasi/proxy/API diperiksa pada layer tes masing-masing.
Foto valid dan failure divalidasi oleh backend tests serta DOM tests, bukan preview visual galeri berisi.
Filter tersimpan selama halaman terbuka dan belum diserialisasi ke URL. Batas workspace foto yang
lebih kecil dari 8 MiB/jumlah foto tetap diberitahukan melalui response backend. Pemilihan primary
manual/edit metadata foto tidak ditambahkan. Tidak ada pekerjaan hardening Task 1A-05 dimulai.

## Langkah review

1. Login dengan akun existing, buka `/catalog/models` dari workspace. Database katalog development
   tetap kosong; gunakan database uji terpisah bila ingin menjalankan mutasi demonstrasi.
2. Review API client/CSRF, ModelForm baseline version, Gallery partial success, dan gate role server.
3. Ulangi npm run check pada web-check dan pytest SQLite/PG memakai perintah di atas.
4. Review tampilan kosong/loading/error, mobile, form specs, dan pembatasan OFFICER/VIEWER.
5. Berikan approval terpisah sebelum Task 1A-05. Pekerjaan berhenti pada 1A-04.
