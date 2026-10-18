# Testing and development dependencies

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