# Sprint 1A-03 — Private local image storage

Tanggal: 18 Oktober 2026 (Asia/Makassar).
Status: implementasi dan pengujian selesai, berhenti sebelum Task 1A-04.
Belum commit/push. Tidak membuat halaman UI katalog, AI/OCR, atau unit aset.

## Review 1A-02 dan keputusan arsitektur

AGENTS.md, spesifikasi Sprint 1A, laporan 1A-02, README, aturan bisnis/arsitektur,
model/migrasi/auth/RBAC, konfigurasi, proxy, dan pola pengujian diperiksa. Graph MCP dicoba
lebih dahulu; proyek belum terindeks, sehingga inspeksi memakai file lokal. Tidak mengulang
indexing yang ditolak pada task sebelumnya. Tidak ada masalah blocking pada hasil 1A-02.
Regresi awal SQLite lulus 156 passed, 1 skipped; Alembic check development cocok dengan model.
Working tree awal memuat hasil 1A-01/02 yang belum di-commit; semuanya dipertahankan.

Metadata device_reference_images sudah tersedia. Task ini menambah StorageProvider dan
LocalStorageProvider serta decoder/parser bounded; file privat terpisah dari PostgreSQL.
Provider memakai key UUID acak, exclusive create, mode file 0600, fsync, dan no-follow
untuk pembacaan; nama/path dari client tidak digunakan. Tidak ada mount static publik/cloud.

Filesystem dan DB tidak mempunyai commit atomik bersama. Untuk menutup gap crash/failure,
migrasi baru **0003_image_cleanup** hanya menambah tabel intent storage_cleanup_jobs.
Intent upload durable sebelum penulisan file, lalu dihapus saat metadata/audit commit.
Delete metadata + intent commit lebih dahulu, kemudian unlink. Kegagalan unlink tetap
tercatat untuk retry; bytes yang metadata-nya sudah hilang tidak dapat diakses melalui API.
Tidak menambah worker, Redis, atau layanan baru. Migrasi lama tidak diubah.

## Perilaku yang tersedia

- ADMIN: multipart upload dan delete; semua role aktif: list metadata dan serve content.
- Auth, Origin, dan CSRF sesi memakai fondasi existing; anonim ditolak sebelum parsing upload.
- JPEG/PNG/WebP saja, magic bytes cocok dengan MIME, verify dan decode penuh, single frame.
- Default 8 MiB input/output; sisi 8192, 16 juta pixel, 20 foto/model; configurable dan bounded.
- Decode diserialisasi per proses; tidak ada kebutuhan GPU.
- Re-encode pixel bersih setelah menerapkan EXIF orientation; EXIF/GPS, ICC/text/XMP,
  dan trailing payload tidak diteruskan. Hash/ukuran mengacu pada bytes hasil sanitasi.
- Model version wajib pada upload/delete; lock PostgreSQL menjaga count/primary/version.
- Foto pertama primary; delete primary mempromosikan foto tersisa paling awal.
- Archive mempertahankan foto; archived dapat dibaca/delete eksplisit tetapi tidak menerima upload.
- Response metadata hanya public fields + content_url relatif; tidak memuat storage_key/path host.
- Content read memeriksa sesi, pasangan model/image, hash, dan ukuran; no-store/nosniff.
- Cleanup gagal dapat diulang melalui CLI; grace 10 menit, maksimum 100 intent/run,
  skip lock aktif, dan selalu melindungi file yang masih direferensikan DB.
- Proxy mendukung multipart/binary/delete tanpa membuka arbitrary route; CRUD tetap 16 KiB,
  upload ceiling 8 MiB + 64 KiB, termasuk request tanpa Content-Length.

Kontrak request/response, status error, batas konfigurasi, dan prosedur retry ada di
API_CONTRACT.md dan README.md.

## Berkas berubah pada task ini

| Berkas | Tujuan |
|---|---|
| apps/api/app/storage.py (baru) | Protocol dan local provider privat |
| apps/api/app/image_validation.py (baru) | Signature/decode/bounds/sanitasi/hash |
| apps/api/app/image_routes.py (baru) | Upload/list/content/delete dan kontrak OpenAPI |
| apps/api/app/image_service.py (baru) | Version/locks, metadata/audit, intent dan retry |
| apps/api/app/storage_cleanup.py (baru) | CLI retry intent lama |
| apps/api/app/catalog.py | Model StorageCleanupJob; model katalog lama hanya diformat bila perlu |
| apps/api/app/models.py | Registrasi model cleanup |
| apps/api/app/main.py | Registrasi router gambar |
| apps/api/app/routes.py | Readiness revisi/tabel baru |
| apps/api/app/config.py | Validasi konfigurasi storage dan resource limits |
| apps/api/migrations/versions/0003_image_cleanup.py (baru) | Migrasi aditif reversible |
| apps/api/requirements.txt | Pillow 13.0.0, python-multipart 0.0.32 |
| apps/api/requirements.lock | Pin paket runtime baru |
| apps/api/requirements-dev.lock | Pin paket runtime yang sama pada image test |
| apps/api/Dockerfile | Direktori storage dimiliki user runtime |
| compose.yaml | Volume reference_images dan environment limits |
| .env.example | Environment baru tanpa rahasia |
| apps/api/tests/test_images.py (baru) | Validasi, authorization, I/O, failure, retry, concurrency |
| apps/api/tests/test_config.py | Batas environment gambar |
| apps/api/tests/test_health.py | Menolak revisi 0002 yang kini lama |
| apps/api/tests/test_migrations.py | Head baru dan preservasi katalog saat roundtrip |
| apps/api/tests/test_catalog_api.py | OpenAPI kini mengakui route gambar |
| apps/web/lib/proxy.ts | Allowlist image, batas stream, binary/header forwarding |
| apps/web/tests/proxy.test.ts | Multipart/content/delete dan stream cap |
| README.md | Konfigurasi, volume, cleanup, backup |
| docs/API_CONTRACT.md | Kontrak gambar aktual |
| docs/ARCHITECTURE.md | Batas storage/DB dan flow intent |
| docs/DATABASE.md | Tabel cleanup, status migrasi, backup/restore |
| docs/sprints/SPRINT_1A_03_REPORT.md (baru) | Laporan ini |

Tidak mengubah migration 0001/0002 atau menambahkan gambar perusahaan/akun/kredensial.
Fixture gambar sintetis dibuat saat tes; tidak ada binary foto baru dalam Git.

## Pelestarian data development

Migrasi dijalankan melalui `docker compose run --rm --no-deps -T migrate python -`
dengan program stdin: satu engine.begin transaction, lock_timeout 5 detik,
statement_timeout 30 detik, SHARE lock pada tujuh tabel existing, snapshot count + MD5
seluruh isi baris yang diurutkan UUID, Alembic upgrade/check, lalu assertion snapshot sama.
Kegagalan assertion akan rollback seluruh migrasi. Isi tabel/rahasia tidak dicetak.

Hasil aktual:

```text
No new upgrade operations detected.
Development schema: 0002_device_catalog -> 0003_image_cleanup
Existing rows unchanged: users=1, auth_sessions=1, audit_events=5,
device_categories=0, manufacturers=0, device_models=0, device_reference_images=0
All existing row fingerprints unchanged; Alembic check passed
```

Setelah recreate hanya API/web: db/api/web healthy, revision 0003_image_cleanup (head).
Volume baru assetvision-it_reference_images dibuat; volume PostgreSQL existing dipertahankan.
Probe temporary file anonim di volume berhasil read/write/fsync oleh uid 10001 dan otomatis
dihapus. Tidak menyimpan foto/model/account uji di development. Count tetap seperti di atas,
storage_cleanup_jobs=0 dan persisted reference files=0. CLI cleanup pada backlog kosong: 0.

## Perintah yang dijalankan

Perintah dari root repository di Ubuntu WSL2, melalui PowerShell/wsl:

```bash
git status --short
docker compose ps
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose --profile test build api-test web-check
docker compose --profile test build web-check
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose build api migrate web
# Build final setelah review/perbaikan source:
docker compose --profile test build api-test api migrate

# Suite final pada source yang dikemas dalam image, tanpa bind mount:
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose config --quiet
git diff --check

# Program verifikasi/migrasi transaksional di atas, melalui stdin:
docker compose run --rm --no-deps -T migrate python -
docker compose up -d --no-deps --wait api web
docker compose exec -T api alembic current
docker compose exec -T api alembic check
# Program HTTP/probe/count read-only seperti dijelaskan di bawah, melalui stdin:
docker compose exec -T api python -
docker compose exec -T api python -m app.storage_cleanup
docker compose -f compose.yaml -f compose.test.yaml --profile test stop db-test
docker compose ps
```

Selama iterasi, Ruff format/check/fix dan pytest targeted/full juga memakai source API
read-only di image lokal; format/fix memakai mount writable dengan uid/gid pemilik checkout.
Suite gambar pertama: 45 passed, 1 skipped; kemudian ditambah regresi stream cap backend.
Image final dibangun ulang dan seluruh suite diulang dari image tersebut.

## Hasil final

| Pemeriksaan | Hasil aktual |
|---|---|
| SQLite, image final | **210 passed, 2 skipped** |
| PostgreSQL 16/PostGIS, image final | **212 passed** |
| Alasan skip SQLite | Inspeksi JSONB PostgreSQL dan concurrency row-lock PostgreSQL |
| Migrasi upgrade/check/downgrade/upgrade | Lulus dalam kedua suite, hanya database uji |
| Upload JPEG/PNG/WebP, EXIF orientation/sanitasi/hash, 5 foto/model | Lulus |
| Invalid MIME/magic/truncated/SVG/GIF/animation/bomb/dimensi/pixel/byte/body | Lulus |
| Anonim/OFFICER/VIEWER, CSRF, stale version, archive, pasangan model/image | Lulus |
| Primary promotion, database/audit rollback, partial put, failed unlink/retry | Lulus |
| Crash intent/grace, referenced-file protection, collision/symlink/traversal | Lulus |
| Dua upload PostgreSQL bersamaan dengan version sama | Satu 201, satu 409; satu file tersimpan |
| Ruff / pip check | Lulus / No broken requirements found |
| Frontend ESLint / TypeScript / tes proxy | Lulus / lulus / **10 passed** |
| Build runtime API/migrate/web dan test images | Berhasil |
| Development Alembic current / check | 0003_image_cleanup (head) / tidak ada operasi baru |
| HTTP readiness via API dan proxy | 200 |
| HTTP image list/content/upload/delete anonim via API dan proxy | 401; mutasi memakai CSRF anonim valid |
| Volume private read/write/fsync sebagai uid 10001 | Lulus; probe anonim dibersihkan |
| Count data existing / cleanup jobs / reference files development | Tidak berubah / 0 / 0 |
| Compose config / git diff --check | Exit 0 |

Database db-test dihentikan setelah tes; layanan development db/api/web tetap healthy.
Semua mutasi foto, account sintetis, dan roundtrip destruktif hanya pada database/file sementara.

## Masalah dan batasan

Docker Hub/PyPI dapat diakses; build dependensi pertama lambat karena unduhan ulang
paket, tetapi semua build final berhasil. Tidak memerlukan fallback install pada runtime.
Lint sempat menemukan format/impor factory storage; diperbaiki sebelum image final.
Tidak ada kegagalan tes tersisa. Warning Starlette TestClient/httpx lama dan peringatan
Compose untuk container smoke lama masih ada; tidak menghapus container tersebut otomatis.

Cleanup CLI harus dijalankan operator jika ada intent tertunda; belum ada scheduler/worker.
Delete yang unlink-nya gagal mengembalikan 204 setelah resource DB hilang; bytes privat
menunggu retry. CLI tidak melakukan directory scan atau menghapus file yang tidak tercatat.
Restore/backup harus membawa DB dan volume gambar bersama. Jangan menurunkan revisi 0003
dengan intent tertunda atau menghapus volume tanpa prosedur/backup.

Implementasi lokal memakai primitive POSIX/Linux dan ditujukan untuk Ubuntu WSL2/Docker.
Pilihan primary manual dan editing metadata foto belum tersedia. Endpoint delete tetap
melakukan audit; katalog/model sendiri tetap tidak memiliki hard delete.

CRUD authenticated diuji pada API TestClient dengan PostgreSQL/SQLite terisolasi dan proxy
diuji unit/binary forwarding. HTTP development hanya diuji tanpa mutasi data. Belum ada
end-to-end authenticated upload melalui browser UI karena UI katalog belum dikerjakan.

## Langkah review

1. Review image_routes.py, image_validation.py, image_service.py, storage.py, dan migration 0003.
2. Review API_CONTRACT.md untuk multipart/version, status errors, primary, dan cleanup semantics.
3. Ulangi pytest SQLite/PostgreSQL serta npm run check pada service test, bukan database aplikasi.
4. Pastikan backup membawa volume reference_images dan gunakan CLI retry bila backlog muncul.
5. Beri approval terpisah sebelum Task 1A-04. Task berikutnya belum dimulai.

Referensi primer: [Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html),
[Pillow PyPI](https://pypi.org/project/Pillow/),
[python-multipart PyPI](https://pypi.org/project/python-multipart/).
