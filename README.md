# AssetVision IT

Fondasi inventaris dan audit aset IT yang berjalan lokal di Ubuntu WSL2.
Stack: Next.js App Router/TypeScript, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16/PostGIS.
Fondasi Sprint 0 mencakup akses pengguna, izin, health check, migrasi, dan audit autentikasi.
Sprint 1A-01 sampai 1A-05 menambahkan skema, CRUD API katalog, foto referensi lokal privat,
UI katalog, dan pemeriksaan hardening. Task 1B-01 menambahkan skema unit fisik,
identifier dan audit metadata. Task 1B-02 menambahkan CRUD API aset/identifier, RBAC,
version dan snapshot audit transaksional. Task 1B-03 menyediakan API CSV preview/commit/export
khusus ADMIN dengan receipt idempotency persisten. Task 1B-04 menyediakan UI daftar/detail,
form unit/identifier, riwayat metadata, dan upload CSV dengan preview serta konfirmasi.
Kontrak tersedia di docs/API_CONTRACT.md.

Setelah login, buka `/catalog/models` atau tautan katalog di workspace untuk mencari,
memfilter, dan membaca model beserta foto referensinya. ADMIN dapat menambah model,
mengedit detail, mengarsipkan/memulihkan model, serta mengunggah/menghapus foto.
Kategori dan produsen dikelola ADMIN melalui `/catalog/settings`.
OFFICER/VIEWER memiliki tampilan baca saja; API tetap memeriksa semua izin.
Konflik perubahan mempertahankan isian agar dapat diperiksa sebelum memuat ulang.

Registry unit fisik tersedia di `/assets`. Gunakan pencarian Asset ID/SN/MAC, filter model/status,
dan pagination; ADMIN dapat menambah/edit/archive, mengelola identifier, serta mengunduh CSV
sesuai filter. Form edit mempertahankan version awal. SN kosong/rusak tidak membuat SN palsu.
Riwayat detail menampilkan aktor UUID, waktu, dan snapshot sebelum/sesudah perubahan.
Impor di `/assets/import` membaca berkas UTF-8 maksimal 256 KiB/500 baris. Tinjau error dan
akui benturan identifier secara eksplisit sebelum konfirmasi. Bila commit terputus, tetap di
halaman dan gunakan retry permintaan yang sama; jangan mulai batch baru atau reload dulu.
Kunci/payload retry hanya bertahan selama halaman terbuka. Export adalah laporan, bukan template
impor. `location_hint` hanya staging. Foto unit opsional belum tersedia; foto referensi model
tetap ada di katalog. Task 1B-05 menambahkan seed delapan AP sintetis eksplisit dan pengujian
hardening/audit serta regresi Sprint 0/1A/1B.

## Seed contoh Sprint 1B

Gunakan hanya pada database development/demo yang memang akan menerima data sintetis.
Seed tidak berjalan otomatis saat startup/migrasi dan menolak APP_ENV=production.
Pilih UUID ADMIN aktif existing sebagai aktor; tidak membuat akun atau kredensial baru:

```bash
docker compose exec api python -m app.seed_assets --actor-id UUID_ADMIN_AKTIF --confirm-synthetic
```

Perintah membuat kategori Access Point (`access-point`), produsen Ruijie dan model `AP680-L`
jika belum ada, lalu tepat delapan contoh `AP-001`…`AP-008` untuk model itu. Existing katalog
aktif dipakai tanpa mengubah metadata. AP-001/AP-002 memakai SN contoh 123456789/2158763;
AP-004/AP-005 tanpa SN. Semua unit/identifier ditandai SYNTHETIC, bukan data produksi.
MAC memakai prefix locally administered `02`, hostname memakai domain `.invalid`.
Total 22 klaim IMPORT/UNVERIFIED dan 30 event audit aset, ditambah audit katalog bila dibuat.

Seed adalah satu transaksi. Benturan kode/UUID/identifier, referensi archived, model yang
sudah mempunyai unit lain, atau batch parsial membuat seluruh seed ditolak tanpa overwrite.
Pengulangan batch lengkap menjadi no-op, termasuk mempertahankan edit user sesudah seed;
tidak memperbaiki/menghidupkan klaim/arsip otomatis. Penambahan unit lain ke model sesudahnya
boleh melalui API normal, tetapi seed ulang akan menolak membership yang berubah.

## Mulai dari Ubuntu WSL2

1. Pasang Ubuntu WSL2 di Windows (`wsl --install -d Ubuntu` dari PowerShell administrator), kemudian aktifkan systemd bila diperlukan:
   tambahkan dua baris `[boot]` dan `systemd=true` pada `/etc/wsl.conf`, lalu jalankan `wsl --shutdown` dari Windows.
2. Pasang Docker Engine dan plugin Compose menggunakan [panduan resmi Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
   Gunakan satu daemon Docker; proyek tidak membutuhkan Docker Desktop. Jalankan `sudo systemctl enable --now docker`.
   Bila memilih grup docker, jalankan `sudo usermod -aG docker "$USER"` dan buka ulang sesi Ubuntu.
   Keanggotaan grup docker memberikan hak setara root.
3. Simpan checkout di filesystem Linux, misalnya `~/projects/assetvision-it`, bukan di `/mnt/c`.
4. Dari terminal **Ubuntu**, jalankan:

```bash
cd ~/projects/assetvision-it
python3 infra/init-env.py
docker compose up -d --build
docker compose ps -a
docker compose exec api alembic current
docker compose exec api python -m app.bootstrap --email you@example.com --name "Administrator"
```

Ganti email dan nama dengan identitas Anda. Perintah terakhir meminta kata sandi dua kali melalui prompt tersembunyi (12–128 karakter).
Tidak ada akun bawaan atau pendaftaran publik. Bootstrap hanya membuat admin saat tabel pengguna kosong.
Pemanggilan ulang untuk admin aktif yang sama tidak mengganti nama, kata sandi, atau peran; akun lain tidak dipromosikan.

Buka [login](http://localhost:3000/login). API langsung tersedia di [health](http://localhost:8000/api/v1/health),
[ready](http://localhost:8000/api/v1/ready), dan [OpenAPI](http://localhost:8000/docs).
Browser memakai proxy `/api/v1/*` di port 3000. Gunakan hostname yang konsisten saat login.

`init-env.py` membuat rahasia acak secara lokal, tanpa mencetaknya. Rahasia non-placeholder lama dipertahankan.
Berkas .env yang formatnya tidak valid disalin ke `.env.backup-sprint0` (diabaikan Git) sebelum dibuat ulang.
Jangan mengganti POSTGRES_PASSWORD untuk volume yang sudah diinisialisasi tanpa prosedur perubahan password database.

## Siklus operasi

```bash
docker compose logs --tail=100 api web migrate
docker compose exec api alembic upgrade head
docker compose stop
docker compose start
# Menghapus container dan network, mempertahankan volume database:
docker compose down
```

Compose menjalankan layanan migrasi sekali sebelum API, lalu menunggu readiness API sebelum memulai web.
Tidak ada schema auto-create pada startup aplikasi. Volume `assetvision-it_postgres_data` menyimpan database.
Jangan gunakan `down -v` pada data yang ingin dipertahankan.

## Pengujian

Semua dependensi pengujian berjalan di container; Node/Python lokal tambahan tidak wajib.
Gunakan image khusus api-test/web-check. Layanan api/web memakai image runtime dan tidak
menyertakan pytest, ESLint, atau compiler TypeScript.

Perintah lengkap yang membangun image lalu menjalankan pemeriksaan:

```bash
bash infra/check.sh --postgres
# Smoke katalog lengkap melalui Next.js/API/PostgreSQL asli, data uji sintetis:
bash infra/smoke-catalog.sh
# Smoke CRUD aset melalui proxy/API/DB uji terisolasi:
bash infra/smoke-assets.sh
# Smoke CSV preview/commit/retry/export melalui proxy terisolasi:
bash infra/smoke-asset-csv.sh
# Smoke server-rendered pages, role guards dan riwayat melalui proxy terisolasi:
bash infra/smoke-asset-ui.sh
# Regresi HTTP Sprint 0/1A/1B + CLI seed pada db-test tmpfs yang dibuat ulang:
bash infra/smoke-sprint1b.sh
```

Tanpa --postgres, script menjalankan backend SQLite, Ruff, ESLint, TypeScript, dan pengujian frontend.
Smoke katalog membangun image dan memakai db-test tmpfs serta storage foto tmpfs khusus api-smoke.
Script menghentikan layanan smoke/db-test saat selesai, termasuk bila gagal; development tetap berjalan.
Setiap run memakai akun/nama sintetis baru sehingga dapat diulang tanpa reset tabel.
Jangan menjalankannya bersamaan dengan suite PostgreSQL yang mereset database uji.
Panduan target image, lockfile, dan diagnosis tersedia di [docs/TESTING.md](docs/TESTING.md).

```bash
docker compose --profile test build api-test web-check
# Backend cepat dengan SQLite in-memory dan migrasi Alembic:
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps web-check npm run check
# Build produksi (juga melakukan pemeriksaan TypeScript Next.js):
docker compose build web

# Backend yang sama + validasi migrasi di PostgreSQL/PostGIS terisolasi:
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test
# Smoke HTTP terhadap API + Next.js asli; jalankan sesudah suite integrasi:
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test up -d web-smoke
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test run --rm api-test python tests/smoke_stack.py
# Hentikan layanan pengujian saja:
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test stop web-smoke api-smoke db-test
```

Database pengujian bernama `assetvision_test`, berada di container terpisah, tanpa port host.
Fixture pengujian menghapus tabel hanya di database terisolasi tersebut.
Pengujian migrasi mencakup upgrade, kesesuaian model (`alembic check`), downgrade, dan upgrade ulang.
TEST_DATABASE_URL wajib menunjuk tepat ke db-test/assetvision_test; password diambil dari environment POSTGRES_PASSWORD dan dirangkai secara aman. Jangan arahkan pengujian ke database aplikasi. Jalankan ulang suite integrasi sebelum mengulang smoke agar data uji kembali bersih.

## Environment

Semua nilai berada di `.env` lokal yang tidak boleh masuk Git. Lihat [.env.example](.env.example).

| Variabel | Default / ketentuan |
|---|---|
| APP_ENV | development; test atau production juga didukung |
| POSTGRES_DB | assetvision; mengubahnya tidak memigrasikan volume lama |
| POSTGRES_USER | assetvision; akun pemilik database/migrasi lokal |
| POSTGRES_PASSWORD | Wajib; dibuat acak oleh init-env.py |
| JWT_SECRET | Wajib; minimal 32 karakter acak; dibuat oleh init-env.py |
| ACCESS_TOKEN_EXPIRE_MINUTES | 15; rentang 1–30 |
| COOKIE_SECURE | false untuk HTTP localhost; wajib true untuk production/HTTPS |
| ALLOWED_ORIGINS | http://localhost:3000,http://127.0.0.1:3000; tanpa slash penutup |
| LOG_LEVEL | INFO; DEBUG, WARNING, ERROR juga didukung |
| IMAGE_STORAGE_ROOT | /var/lib/assetvision/uploads; absolut; Compose menetapkan lokasi ini dalam volume reference_images |
| IMAGE_MAX_BYTES | 8388608 (8 MiB); 1024–8388608; input dan hasil sanitasi |
| IMAGE_MAX_DIMENSION | 8192; panjang sisi maksimum; 64–16384 |
| IMAGE_MAX_PIXELS | 16000000; jumlah pixel maksimum; 4096–24000000 |
| IMAGE_MAX_PER_MODEL | 20; jumlah foto maksimum per model; 5–100 |
| POSTGRES_HOST | db, ditetapkan Compose untuk API/migrasi |
| POSTGRES_PORT | 5432, hanya jaringan Docker; tidak dipublikasikan |
| DATABASE_URL | Opsional untuk API di luar Compose; URL SQLAlchemy; mengungguli komponen POSTGRES_* |
| INTERNAL_API_URL | http://api:8000; hanya sisi server Next.js, tidak dikirim ke browser |
| TEST_DATABASE_URL | Hanya pengujian; ditetapkan compose.test.yaml ke DB sementara |
| NEXT_TELEMETRY_DISABLED | 1 di container web |
| HOSTNAME / PORT / NODE_ENV | Runtime web: 0.0.0.0 / 3000 / production |

ADMIN_PASSWORD tidak digunakan sebagai environment variable. Password hanya melalui prompt bootstrap.

Foto tidak dipublikasikan sebagai direktori static. Akses melalui endpoint berautentikasi.
Volume `reference_images` harus dicadangkan bersama database. Retry cleanup yang gagal:
`docker compose exec api python -m app.storage_cleanup` (maks. 100 intent berusia >10 menit).
Perintah ini hanya memproses intent tersimpan dan melindungi key yang masih direferensikan DB.
Jangan mengubah IMAGE_STORAGE_ROOT tanpa memindahkan file dan merencanakan backup/restore.
Mengganti JWT_SECRET membatalkan token lama. Tidak ada refresh token atau penyimpanan token di localStorage.
Aplikasi lokal ini belum menyediakan pengelolaan pengguna, pemulihan kata sandi, atau pembatasan percobaan login.
Jangan publikasikan port pengembangan ke jaringan umum.

## WSL2 dan troubleshooting

- `permission denied /var/run/docker.sock`: periksa grup docker, atau jalankan perintah Docker dengan sudo.
- Daemon belum berjalan: `sudo systemctl status docker`; periksa dukungan systemd WSL.
- Port 3000/8000 terpakai: hentikan layanan yang bentrok atau ubah sisi host pemetaan port. Jika port web diubah, sesuaikan ALLOWED_ORIGINS dan buat ulang container API.
- Login 403: gunakan origin yang didokumentasikan; ambil token CSRF dari endpoint sebelum POST; jangan memakai cookie dari hostname lain.
- Login 401: periksa email/password, status aktif, dan masa berlaku sesi. Jalankan bootstrap bila database masih kosong.
- Readiness 503 / web belum dimulai: periksa log db dan migrate. Jalankan migrasi yang gagal setelah memperbaiki penyebabnya.
- Password database berubah di .env tetapi koneksi gagal: variabel image PostgreSQL hanya berlaku saat volume kosong. Pulihkan konfigurasi lama dan rencanakan ALTER ROLE secara eksplisit; jangan menghapus volume.
- Build awal membutuhkan akses internet untuk image Docker serta paket Python/npm. Tidak ada layanan cloud saat runtime.
- Untuk RAM 16 GB, opsional gunakan `%UserProfile%/.wslconfig` dengan `[wsl2]`, `memory=8GB`, `processors=4`, `swap=2GB`, lalu `wsl --shutdown`. Build membutuhkan lebih banyak RAM sementara daripada runtime.
- Batas runtime Compose: database 768 MB, API 512 MB, web 512 MB; satu worker API, pool koneksi kecil. GPU tidak diperlukan.

Dokumen lanjutan: [arsitektur](docs/ARCHITECTURE.md), [aturan bisnis](docs/BUSINESS_RULES.md),
[database](docs/DATABASE.md), dan [kontrak API](docs/API_CONTRACT.md).
