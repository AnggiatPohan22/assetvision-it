# Sprint 3-02 — Versioned embedding index

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Scope hanya Task3-02. Task3-03 OCR tidak dimulai. Belum commit/push.
Status: implementasi, regresi penuh, CPU integration, smoke, migration dan preservasi final selesai.
Encoder/threshold produksi tetap belum dipilih; gate NO_GO3-01 dipertahankan.

## Review hasil Task 3-01

Awal working tree bersih di main `c9c25e61dc8b9da30e5561da58b50e45906144ce`, satu commit
lokal di atas origin/main3c4adb9. Task3-01 sudah menyediakan manifest/leakage/evaluation
harness, dua pretrained CPU candidates dan baseline agregat, tetapi **NO_GO memilih encoder
atau threshold produksi**. Enam foto WP810 hanya cukup untuk profil CPU satu model; geometri
sintetis tidak membuktikan accuracy perangkat atau unknown rejection.

AGENTS.md, README, Sprint3, laporan/penutupan3-01, architecture/business/database/API/testing,
model/schema/migration/storage/image/auth dan pola test/Compose ditinjau sebelum implementasi.
MCP graph list_projects hanya berisi payload-cms-villa, maka sumber lokal dipakai. Memori
membantu batas task/isolasi WSL; keadaan Git/data/schema diperiksa langsung.

Permintaan baru mengotorisasi implementasi3-02, bukan promosi hasil NO_GO menjadi pilihan
encoder. Solusi: adapter eksplisit tanpa default, index generation terpisah dari master,
uncalibrated UNCERTAIN, dan policy hanya melalui report real yang direview ADMIN.
Tidak menambah AI generatif, GPU wajib, OCR, fusion, survey/review API atau UI.

## Rancangan dan implementasi

- Protocol ImageEncoder + frozen Pydantic EncoderSpec menyimpan name/version, full weight SHA,
  preprocessing hash dan dimensi. Dua adapter CPU opsional: MobileNetV3 Small576 dan ShuffleNet
  V2 0.5x1024, PyTorch2.10.0+cpu/torchvision0.25.0+cpu pinned. Constructor memerlukan nama
  eksplisit; cache/versi/SHA tidak cocok ditolak tanpa download. Startup API tidak import torch.
- Decoder bounded JPEG/PNG/WebP memeriksa MIME/magic, <=IMAGE_MAX_BYTES (8MiB default), satu
  frame, sisi<=4096 dan <=16Mpixel, EXIF orientation+RGB. Tidak re-encode/overwrite foto sumber,
  menyimpan EXIF, mengunggah atau mencatat isi foto. Embedding L2, dimensi/nonfinite/zero ditolak.
- Migration0010_embedding_index hanya menambah embedding_indexes, image_embeddings dan
  embedding_index_state(id1,current_index_id=null,version1). Generation menyimpan spec/policy/
  source fingerprint/actor/time; row vector menunjuk parent generation. PostgreSQL JSONB,
  tanpa pgvector atau dependency baru pada API default.
- Index/vector historis immutable UPDATE/DELETE; SQL guard insert menjaga sumber/model/hash
  dan kapasitas. Delete foto existing tetap kompatibel: current reference FK SET NULL, tetapi
  snapshot UUID/hash/vector historis dipertahankan. Tidak mengubah API/logic foto existing.
  Head hanya bergeser version+1; populated downgrade ditolak untuk menjaga evidence.
- Rebuild ADMIN aktif memakai expected_version+reason, snapshot katalog satu query, membaca
  StorageProvider existing dan mencocokkan bytes/size/SHA. CPU di luar transaksi/lock. Sebelum
  publish cek ulang actor/source/spec/head; generation+seluruh vector+head/audit satu commit.
  Fail/stale/rollback tidak menimpa generation lama. Dua rebuild CAS: satu berhasil, satu409.
- Query semua user aktif, read-only. Per-model maximum cosine, model unik, tie UUID stabil,
  top_k1..10/default3. Version/head/fingerprint/spec diperiksa sebelum/sesudah CPU; stale,
  mismatch atau invalid artifact tidak memaksa kandidat. Tidak ada asset ID/VERIFIED atau
  perubahan lokasi/identifier/metadata/master dari hasil similarity.
- Empty index UNKNOWN_MODEL; uncalibrated UNCERTAIN + ranking informasional; calibrated
  max similarity di bawah threshold UNKNOWN_MODEL tanpa kandidat; lolos berarti
  KNOWN_MODEL_CANDIDATE, bukan unit fisik atau confidence terkalibrasi setiap alternatif.
- Report kalibrasi wajib real/non-synthetic, eligible/GO, target top3>=90%, split/unknown
  memadai, metrics finite, encoder/preprocess/dimensi tepat dan mapping UUID/reference counts
  cocok. ADMIN mengikat fingerprint snapshot yang ditinjau. Policy menyimpan digest kanonis
  report/dataset/spec/source secara immutable, tidak diwarisi otomatis ke generation berikutnya.
  Ini validasi report+attestation ADMIN, bukan bukti otomatis truth label/split foto eksternal.
  Dataset WP810/geometri existing ditolak sebagai kalibrasi produksi.
- CLI lokal status/rebuild/search dan Compose opt-in recognition; bukan endpoint/browser login.
  Actor UUID attribution untuk operator dengan akses DB, bukan credential HTTP. Rebuild wajib
  --confirm-rebuild dan expected_version. CPU image terpisah memuat weights publik cached,
  storage read-only, internal DB network tanpa port, CPU2/mem2GiB/readonly/tmpfs/cap-drop.

## Berkas perubahan

| Kelompok | Berkas |
|---|---|
| Kontrak dan adapter | apps/api/app/recognition_schemas.py, recognition_encoder.py |
| Persistensi/service | recognition_models.py, recognition_index.py, models.py, migration0010 |
| Operasional opt-in | recognition_cli.py, compose.recognition.yaml, infra/recognition-index/Dockerfile dan Dockerfile.dockerignore, infra/check-recognition-index.sh |
| Readiness/migration regression | routes.py, tests/test_health.py, test_migrations.py, test_asset_csv.py |
| Unit/integration | tests/test_recognition_index.py dan test_recognition_cpu.py |
| Dokumentasi | README, ARCHITECTURE, BUSINESS_RULES, DATABASE, API_CONTRACT, TESTING, RECOGNITION_INDEX, Sprint3 status dan laporan ini |

Source Task3-01 tools/requirements/BASELINE tidak diubah. Tidak mengubah frontend, dependency
runtime API, env atau migration0001–0009. Tidak ada foto/weights/vector nyata/dump di Git.

## Pengujian dan iterasi

Tes mencakup model-level ranking vs reference duplicates, L2/vector invalid, uncalibrated/
unknown/calibrated gate, report synthetic/NO_GO/mismatch, role/revocation, head/source stale,
audit/storage/encoder rollback, immutable SQL, compatibility photo FK delete, empty index,
head/migration/readiness, concurrent PG rebuilds dan perubahan actor/source/head selama CPU.

Initial targeted SQLite menemukan test helper membaca UUID ORM expired setelah assignment
draft sehingga SQLAlchemy autoflush sebelum service dipanggil. Tes diperbaiki dengan UUID
captured sebelum draft, untuk benar-benar menguji clean transaction boundary. Kasus revocation
memerlukan import User pada fixture baru. Ruff format/import/line length diselesaikan.

CPU integration memakai dua adapter/weights nyata dan gambar generated. Query foto referensi
sendiri hanya self-match untuk mengecek plumbing, bukan accuracy held-out. CLI subprocess nyata
pada SQLite file terisolasi menguji status→rebuild→search UNCERTAIN→stale409. Missing/corrupt
weight menolak tanpa network. Default API tidak memiliki torch dan CPU tests di-skip di sana.

Percobaan full pertama lulus SQLite/frontend tetapi gagal pada pembuatan ulang fixture PG:
fungsi trigger0010 memakai CREATE FUNCTION sedangkan Base.metadata.drop_all tidak menghapus
function. Runner test PG itu dihentikan; tidak menghentikan/mengubah database development.
Migration baru (belum diterapkan development) diperbaiki ke CREATE OR REPLACE sesuai pola
existing. Tes PG terarah kemudian **58 passed** (32.95detik), termasuk race dan roundtrip.
Full runner diulang terhadap source final. Warning Starlette/httpx dan Compose orphan existing
bukan error baru; tidak menghapus service lain atau mengubah dependency untuk menutupinya.

## Perintah aktual

Dari root Ubuntu WSL2, source ditulis di WSL. Test memakai api-test/web-check, bukan runtime.
Output panjang disimpan /tmp; tidak mencetak .env/credential.

```bash
git status --short --branch
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py > /tmp/av-sprint3-02-before.json
docker compose ps -q db > /tmp/av-sprint3-02-db-id
docker compose --profile test build api-test
docker compose --profile test run --rm --no-deps api-test python -m pytest -q tests/test_recognition_index.py tests/test_health.py tests/test_migrations.py
# Ruff format/check pada bind /src, workdir /src dan konfigurasi repo existing.
bash infra/check-recognition-index.sh
bash infra/check.sh --postgres
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -x -q tests/test_recognition_index.py tests/test_migrations.py
# Sesudah perbaikan fixture PG, full runner dan CPU integration dijalankan kembali.
bash infra/check.sh --postgres
bash infra/check-recognition-index.sh
docker compose build api migrate
docker compose config --quiet
docker compose -f compose.yaml -f compose.recognition.yaml --profile recognition config --quiet
bash -n infra/check-recognition-index.sh
git diff --check
```

## Hasil akhir dan preservasi

- Full runner final `bash infra/check.sh --postgres`: **exit0**. Pip check No broken
  requirements found, Ruff All checks passed. SQLite **675 passed,27 skipped** (253.32detik);
  PostgreSQL/PostGIS **698 passed,4 skipped** (322.31detik).23 skip SQLite-only PG/race
  dieksekusi pada PG;4 sisanya adalah CPU optional yang diperiksa pada image tersendiri.
- Frontend lint/TypeScript dan **78 passed,0 failed/skipped** (5745.99ms). Tidak ada perubahan
  frontend atau dependency/lockfile API. Default API terbukti torch_installed=False.
- CPU optional final: **4 passed** (36.72detik) pada network none/read-only/private SQLite,
  termasuk dua adapter nyata, missing/corrupt/no-download dan CLI subprocess end-to-end.
- Enam smoke serial semuanya exit0: Sprint0/1A/1B20, locations2, initial placement2,
  movements3, observations3, location-ui4; total **34 kelompok PASS**. Guard target db-test/
  assetvision_test dipertahankan dan test services berhenti setelahnya. Tidak mengklaim
  manual browser UAT baru karena tidak ada UI baru; SSR/proxy smoke nyata tetap dijalankan.
- 95 source Python app/migrations/tests dicocokkan byte/hash dengan image api-test, runtime
  API dan CPU CLI; semuanya identik. Manifest lokal /tmp/av-sprint3-02-verified-api-source.json.
  Sembilan source harness3-01 juga masih cocok dengan baseline yang sudah dicommit.

Setelah seluruh suite dan PG race lulus, runtime api/migrate dibangun ulang. Migration
`docker compose run --rm --no-deps migrate` diterapkan pada development; API saja diperbarui
melalui `docker compose up -d --no-deps --wait api`. DB tidak recreate/restart; web tidak
perlu recreate. Head **0010_embedding_index**, alembic check **No new upgrade operations**.
Tidak menjalankan CLI rebuild/encoder/kalibrasi pada development. Singleton baru benar-benar
id1/version1/current_index_id=null; embedding_indexes dan image_embeddings tetap0 baris.

Fingerprint sebelum/sesudah dibandingkan atas seluruh tabel existing, semua kolom/timestamp/
version/PostGIS/storage. **existingTablesUnchangedExceptRevision=true**; satu-satunya
perbedaan tabel lama adalah revisi Alembic yang memang maju0009→0010. Tiga tabel baru
embedding_indexes0/image_embeddings0/embedding_index_state1 sesuai migration. Storage identik,
identitas container DB identik dan hash12 foto/sidecar WP810 identik. Tidak ada pengecualian
users/session/audit/aset/identifier/lokasi/movement/observation atau kolom bisnis existing.

Probe anonim read-only: ready200, observation inbox401, /assets,/locations,/movements307
ke/login. API/web/db healthy, DB internal tanpa port host, API/web bind127.0.0.1. Tidak ada
login/bootstrap/seed/backfill/placement/movement/review development, penggantian .env/JWT/
password atau pemetaan foto WP810 ke katalog. Query/rebuild hanya diuji pada data sintetis
terisolasi; foto nyata tidak disalin/diubah atau dimasukkan Git.

Perintah operasional final tambahan:

```bash
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps --wait api
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py > /tmp/av-sprint3-02-after.json
# Comparator read-only: hanya alembic_version berubah; new tables0/0/1, storage/DB id/foto sama.
python3 /tmp/av-20261019-2-05-probe.py
bash infra/smoke-sprint1b.sh
bash infra/smoke-locations.sh
bash infra/smoke-asset-locations.sh
bash infra/smoke-movements.sh
bash infra/smoke-observations.sh
bash infra/smoke-location-ui.sh
docker compose ps
git diff --check
git diff --cached --stat
```

Log aktual: /tmp/av-sprint3-02-final-full.log, verified-cpu.log, pg-target.log,
smoke-{sprint1b,locations,asset-locations,movements,observations,location-ui}.log,
migrate-development.log dan development-api.log (semua memakai prefix av-sprint3-02-).
Tidak menjalankan dua writer/suite bersamaan pada db-test. CPU integration memakai private
SQLite, bukan PG/development. Index Git kosong; tidak commit/push atau mulai task berikutnya.

## Batas

NO_GO pemilihan encoder/threshold produksi3-01 tetap berlaku. Belum ada accuracy real/unknown
rejection yang dibuktikan. Source snapshot maksimum5000row, eligible reference maksimum2000,
full rebuild tanpa incremental cache/pruning. Metadata version/arsip model lokal konservatif:
perubahan source apa pun memerlukan rebuild. Vector validation bukan proteksi terhadap DB owner
yang dapat menonaktifkan trigger. Tidak ada klaim benchmark maksimum/SLA runtime.

Report calibration yang dideklarasikan belum membuktikan label/independensi dataset; operator
harus meninjau data dan mengikat reference fingerprint yang benar. Model candidate bukan unit
identity. Tidak memulai OCR/Task3-03 atau task berikutnya. Tidak commit/push pada implementasi.


## Review akhir implementasi

Seluruh26 berkas tracked/baru berada dalam Task3-02; tidak ada temuan penghalang pada review
akhir. Whitespace/newline/diff check bersih, index Git kosong.95 source Python masih identik
dengan image teruji; foto/sidecar dan keempat report benchmark privat3-01 juga tetap cocok
hash baseline. Fingerprint final setelah semua smoke identik byte dengan checkpoint sesudah
migration, termasuk tiga tabel baru dan revisi0010. Tidak ada data bisnis berubah di sela tes.

Tidak ada langkah manual wajib tersisa untuk verifikasi teknis3-02. Penggunaan encoder dan
kalibrasi nyata tetap opt-in setelah dataset/review yang memadai, bukan aktivasi otomatis.
Task3-03 tidak dimulai; semua perubahan implementasi masih unstaged dan belum commit/push.


## Review penutupan dan commit lokal

Review diff akhir Task3-02 tidak menemukan temuan penghalang. Catatan unstaged/tidak commit
pada bagian implementasi di atas merekam keadaan sebelum permintaan commit dari pengguna.
Sumber aplikasi tidak berubah setelah pengujian final: seluruh95 hash source API cocok
manifest versi teruji. Log final dikonfirmasi ulang: SQLite675passed/27skipped,
PostgreSQL698passed/4skipped, frontend78passed/0failed, CPU4passed. Suite penuh tidak
diulang karena tidak ada perubahan source setelah pengujian tersebut.

Fingerprint read-only terbaru `/tmp/av-sprint3-02-commit-review.json` identik byte dengan
`/tmp/av-sprint3-02-final.json`; seluruh12 hash foto/sidecar juga tetap cocok baseline.
API, web dan database healthy. Tidak ada perubahan data existing dalam review commit ini.
Perintah review meliputi `git diff --check`, review diff/source, pemeriksaan hash dengan
Python, pembacaan log pengujian final, `docker compose ps`, serta pengambilan fingerprint
melalui `docker compose exec -T api python -` dengan skrip read-only yang sama.

Commit lokal hanya mencakup26 berkas Task3-02 yang disebut dalam laporan. Staging memakai
path eksplisit, dilanjutkan `git diff --cached --check`, pemeriksaan daftar staged dan
`git commit -m "feat: implement Sprint 3-02 versioned embedding index"`.
Tidak push dan tidak memulai Task3-03. Gate NO_GO pemilihan encoder/threshold produksi
serta hasil UNCERTAIN tanpa kalibrasi tetap berlaku.
