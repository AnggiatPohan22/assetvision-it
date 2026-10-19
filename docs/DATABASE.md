# Database

## Task 2-01 — locations

Revisi `0006_locations` (parent `0005_asset_imports`) menambah tabel locations kosong:
UUID PK, parent_id self FK RESTRICT, code/name/kind, is_active, latitude/longitude nullable,
gps_accuracy_m/gps_recorded_at nullable, created_at/updated_at, created_by/updated_by FK users,
version ORM positif. Partial unique index root code dan parent_id+code meliputi lokasi arsip;
index parent_id untuk child lookup. CHECK berpasangan/rentang koordinat dan no-self-parent.
Trigger recursive CTE mencegah cycle; trigger lain/terpadu menolak UUID update dan DELETE.
Kode divalidasi pula pada SQL langsung. PostgreSQL advisory key 649237804 digunakan service
dan trigger untuk serialisasi hierarki. Tidak mengedit migrasi 0001–0005.

Upgrade tidak menulis tabel existing, menambah seed, memetakan location_hint, atau memberi
current_location_id kepada aset. Downgrade hanya diizinkan bila locations kosong;
penolakan populated table mencegah hilangnya definisi lokasi. Jangan downgrade development
untuk testing; gunakan db-test tmpfs. Floorplan/pin dan FK lokasi aset belum ditambahkan.

## Seed aset sintetis — 1B-05

Tidak ada perubahan skema/migration pada hardening 1B-05; head tetap 0005_asset_imports.
CLI `python -m app.seed_assets --actor-id UUID_ADMIN_AKTIF --confirm-synthetic` hanya untuk
development/test, tidak dijalankan saat startup. Satu transaksi menambah katalog yang belum
ada, delapan unit AP-001…AP-008, 22 klaim dan 30 asset_change_events. Katalog baru juga
mempunyai catalog_create audit. Ledger CSV tidak digunakan karena seed adalah CLI terpisah.
Unit diberi UUID deterministik; CREATE snapshot marker membuktikan kepemilikan batch seed.
Rerun batch lengkap tidak melakukan UPDATE atau menambah audit; edit sesudahnya dipertahankan.
Benturan atau batch parsial ditolak, tidak ada repair/upsert/delete otomatis.

Preservasi saat seed diperiksa per primary key dan hash tiap baris existing, bukan hanya
jumlah tabel: baris baru yang diharapkan boleh bertambah, seluruh nilai baris lama tetap sama.
Storage file tidak disentuh. Untuk membatalkan contoh yang telah dipakai, archive melalui
API/UI normal agar kode tetap dicadangkan dan audit terpelihara; jangan SQL DELETE/reset volume.

PostgreSQL 16 dengan PostGIS 3.4. Compose tidak mempublikasikan port 5432.
Volume bernama postgres_data menyimpan data; image menginisialisasi database hanya saat volume kosong.

## Schema Sprint 0

| Tabel | Kolom utama dan batasan |
|---|---|
| users | id UUID PK; email varchar(254) unik dan dinormalisasi lowercase; name varchar(100); password_hash Argon2id; role CHECK ADMIN/OFFICER/VIEWER; is_active; created_at UTC |
| auth_sessions | id UUID PK (jti); user_id FK terindeks; csrf_hash SHA256; expires_at terindeks; revoked |
| audit_events | id UUID PK; actor_id FK nullable; action; details JSON; created_at UTC |
| alembic_version | Revisi skema yang dikelola Alembic |

Relasi sesi dan audit tidak memiliki cascade delete, agar riwayat tidak terhapus diam-diam.
UUID dibuat aplikasi. Tidak ada real asset data, foto, serial, lokasi, atau data AI pada migrasi ini.
Sesi kedaluwarsa tetap tidak valid walaupun barisnya masih ada. Kebijakan retensi dan pembersihan
sesi/audit belum diimplementasikan; jangan menghapus audit tanpa kebijakan yang disetujui.

## Migrasi

```bash
docker compose run --rm migrate
docker compose exec api alembic current
docker compose exec api alembic check
```

Revisi awal 0001_sprint0 membuat extension PostGIS bila belum ada dan ketiga tabel.
Akun PostgreSQL lokal menjadi pemilik database agar migrasi extension dapat berjalan.
Pemisahan akun migrasi dan runtime dengan privilege minimum merupakan pekerjaan hardening deployment mendatang.

Downgrade menghapus tabel autentikasi dan audit, sehingga bersifat destruktif:
hanya diuji pada database sementara. Extension PostGIS tidak dihapus oleh downgrade.
Jangan menjalankan downgrade pada database berisi data tanpa persetujuan dan backup.
Koneksi PostgreSQL aplikasi dan Alembic memakai search_path=public agar skema extension tiger/topology tidak ikut dikelola. Alembic mengabaikan spatial_ref_sys yang dimiliki extension saat membandingkan model.

## Schema Sprint 1A-01

Revisi `0002_device_catalog` menambahkan katalog model, bukan unit fisik:

| Tabel | Kolom utama dan batasan |
|---|---|
| device_categories | UUID PK; code varchar(50) unik lowercase tanpa spasi; name varchar(100); description nullable |
| manufacturers | UUID PK; name varchar(150); normalized_name generated lower(trim(name)) unik; website nullable |
| device_models | UUID PK; manufacturer_id/category_id FK terindeks; model_name varchar(200); normalized_model_name generated dan terindeks; unique(manufacturer_id, normalized_model_name); aliases JSONB; description nullable; environment CHECK indoor/outdoor/both; specs JSONB |
| device_reference_images | UUID PK; device_model_id FK terindeks; storage_key relatif unik; sha256 panjang 64; mime_type CHECK JPEG/PNG/WebP; byte_size positif; angle nullable; is_primary; uploaded_by FK users; created_at |

Tiga tabel master memiliki `is_active`, `created_at`, `updated_at`, `created_by/updated_by`
nullable (FK users), dan `version` positif. Nilai awal version 1; SQLAlchemy version counter
menolak update/delete ORM yang stale. Endpoint task 1A-02 mewajibkan version dari client
dan menulis audit dalam transaksi yang sama. Bulk SQL tidak memakai pemeriksaan versi ORM.
`updated_at` diperbarui oleh SQLAlchemy, bukan trigger untuk SQL langsung.

Nama display melalui ORM dirapikan dengan split/join whitespace; kapitalisasi dipertahankan.
Database menghitung sendiri normalized key sehingga tidak dapat dipalsukan oleh caller.
SQL langsung wajib memberi nama nonkosong tanpa spasi tepi/ganda atau tab/newline/CR;
pelanggaran ditolak CHECK. Case-insensitive memakai `lower` database, bukan transliterasi
atau Unicode casefold. SQLite memakai JSON untuk pengujian cepat; PostgreSQL memakai JSONB.
Validasi bentuk/batas aliases dan specs melalui Pydantic tersedia pada task CRUD API 1A-02;
lihat API_CONTRACT.md. SQL langsung tetap menjadi tanggung jawab operator.

FK tidak memakai cascade delete: kategori/manufacturer/model yang direferensikan tidak dapat
dihapus. Archive memakai `is_active=false`; UUID dan reservasi nama tetap dipertahankan.
Gambar memiliki partial unique index: maksimal satu foto primary per model, sementara
beberapa foto non-primary diperbolehkan. Tabel hanya metadata, belum menyimpan/melayani file.
Storage key menolak path absolut Unix/Windows, backslash, dan traversal `..`.
Pemeriksaan magic bytes, dimensi, hash file, dan storage provider masuk task 1A-03.

Seed sintetis bersifat eksplisit, idempotent, dan satu transaksi (advisory lock PostgreSQL):

```bash
# Sesudah image baru dibangun dan migrasi diterapkan:
docker compose exec api python -m app.seed_catalog
```

Seed membuat kategori Access Point, Router, Switch, CCTV, Printer dan manufacturer Ruijie,
Ubiquiti, MikroTik. Tidak membuat model/unit/foto/akun atau mengubah baris yang sudah ada,
termasuk baris nonaktif. Tidak ada seed otomatis saat startup atau migrasi.

Readiness versi baru mensyaratkan revisi `0002_device_catalog` dan keempat tabel tambahan.
Deploy harus membangun API/migrate dari source yang sama, menjalankan upgrade, lalu mengganti
API. API Sprint 0 lama akan menolak readiness sesudah upgrade; jadwalkan pergantian bersama.
Downgrade ke `0001_sprint0` menghapus seluruh data katalog tetapi mempertahankan tabel Sprint 0.
Roundtrip hanya dijalankan pada database pengujian; jangan downgrade data operasional tanpa
persetujuan dan backup. Tidak ada migrasi database aplikasi yang dijalankan oleh task ini.

Pada task **1A-02**, database development telah di-upgrade dari `0001_sprint0` ke
`0002_device_catalog`. Upgrade hanya menambah tabel/index/constraint katalog. Verifikasi
dalam transaksi memastikan jumlah dan fingerprint isi seluruh tabel Sprint 0 tidak berubah
(users=1, auth_sessions=1, audit_events=5). Tidak ada seed development atau migrasi baru untuk
CRUD. Detail eksekusi tersedia di sprints/SPRINT_1A_02_REPORT.md.

## Image storage — Task 1A-03

Revisi `0003_image_cleanup` hanya menambah tabel `storage_cleanup_jobs`:
id UUID PK, storage_key varchar(255) unique, created_at UTC terindeks. Metadata foto tetap
di device_reference_images; file privat di volume Docker `reference_images`, path container
`/var/lib/assetvision/uploads`. File di dalamnya memakai key UUID acak berekstensi jpg/png/webp.
Tidak ada perubahan isi tabel existing pada migrasi ini.
Development telah berada di `0003_image_cleanup`. Upgrade transaksional dan Alembic check
lulus; jumlah serta fingerprint semua tujuh tabel existing tetap sama (users=1, sessions=1,
audit=5, seluruh tabel katalog=0). Tabel cleanup dan volume gambar tetap kosong setelah verifikasi.

Intent upload committed sebelum put/fsync; sukses metadata/audit menghapus intent pada transaksi
yang sama. Gagal upload menghapus file melalui kompensasi; crash/failure menyisakan intent retryable.
Delete metadata dan pembuatan intent cleanup berada dalam satu transaksi sebelum unlink.
Cleanup CLI hanya memproses intent tersimpan berusia >10 menit, maksimum 100/run, dan selalu
melindungi key yang masih direferensikan DB. Tidak melakukan directory scan atau GC file asing.

Backup/restore harus mencakup database **dan** volume reference_images secara terkoordinasi
(hentikan mutasi API saat snapshot). Backup DB saja tidak membawa bytes foto. Jangan menghapus
volume atau memindahkan IMAGE_STORAGE_ROOT tanpa prosedur pemindahan dan backup.
Downgrade 0003 menghapus intent cleanup, bukan foto/metadata existing; pastikan tidak ada
intent tertunda sebelum downgrade operasional. Roundtrip hanya diuji pada database sementara.

## Schema Sprint 1B-01

Revisi `0004_asset_registry` di atas `0003_image_cleanup` menambah tiga tabel, index,
CHECK/FK, serta trigger PostgreSQL (padanan SQLite untuk pengujian). Tidak mengedit migration lama,
memindahkan data katalog, mengisi seed, atau mengubah audit autentikasi/katalog existing.

| Tabel | Kolom dan batasan |
|---|---|
| assets | UUID PK; asset_code varchar(50) unique; device_model_id FK RESTRICT terindeks; lifecycle_status terindeks; condition; notes; purchase_date/installed_at nullable; created_at/updated_at; version positif |
| asset_identifiers | UUID PK; asset_id FK RESTRICT terindeks; identifier_type; raw_value/normalized_value wajib; verification_status; source wajib; notes; created_at; deleted_at nullable; version positif |
| asset_change_events | UUID PK; asset_id/actor_id FK RESTRICT terindeks; event_type; before_json nullable; after_json wajib; recorded_at server timestamp terindeks |

Lifecycle: IN_STOCK (default), IN_USE, MAINTENANCE, RETIRED, ARCHIVED.
Kondisi: UNKNOWN (default), GOOD, DAMAGED, UNUSABLE. Ini vocabulary awal, belum workflow transisi.
Identifier: SERIAL_NUMBER, MAC_LAN, MAC_WLAN, BSSID, HOSTNAME, MANAGEMENT_ID.
Source: MANUAL, IMPORT, CONTROLLER. Verifikasi: UNVERIFIED (default), VERIFIED, DISPUTED.
Event: CREATE, UPDATE, ARCHIVE, IDENTIFIER_ADD, IDENTIFIER_UPDATE, IDENTIFIER_REMOVE.

Partial unique index `(asset_id, identifier_type, normalized_value) WHERE deleted_at IS NULL`
mencegah duplikasi klaim aktif pada unit yang sama. Index `(identifier_type, normalized_value)`
menyediakan lookup collision lintas unit; tidak ada uniqueness global SN/MAC/BSSID.
Baris yang soft-deleted tetap tersimpan; klaim pengganti mendapat UUID baru.
Serial kosong berarti tidak ada klaim serial, bukan baris identifier kosong.
ORM menghitung normalized_value dari raw_value pada insert/update. SQL langsung wajib
menyediakan nilai kanonis; trigger memeriksa format MAC dan kesesuaian normalized/raw.

Trigger menolak perubahan UUID/asset_code dan DELETE aset, perubahan pemilik/UUID klaim,
DELETE identifier, serta UPDATE/DELETE audit. Asset code tetap dipesan setelah archive.
Version ORM tersedia untuk aset dan identifier; API 1B-02 memeriksa request version dan
menulis audit transaksional otomatis. JSONB dipakai untuk snapshot di PostgreSQL, JSON pada SQLite.
Tidak ada kolom lokasi bebas. updated_at dikelola ORM; bulk SQL tidak menaikkan version
atau timestamp secara otomatis. Task 1B-01 tidak membuat API/seed; API ditambahkan oleh 1B-02.

Task 1B-02 tidak mengubah schema/migration: head tetap 0004_asset_registry. Service API
mengunci aset induk untuk mutasi metadata/identifier, memeriksa version client, lalu menaikkan
version unit (dan version klaim pada update/remove) serta mencatat snapshot dalam satu commit.
Tidak menambah tabel audit paralel atau kolom lokasi. Tidak ada seed otomatis.

Readiness source baru mensyaratkan revision 0004 dan ketiga tabel. Deploy berurutan:
build API/migrate dari source sama → upgrade head → recreate API. Web tidak berubah.
Downgrade ke 0003 menghapus seluruh tabel/data aset baru dan function trigger terkait;
tabel/data Sprint 0/1A dipertahankan. Downgrade hanya diuji pada DB sementara; butuh
persetujuan dan backup sebelum dilakukan pada data operasional.

Pada 18 Oktober 2026, development di-upgrade ke 0004 dan API diganti ke image baru.
Alembic current/check lulus. Fingerprint SHA-256 seluruh baris delapan tabel existing dan
seluruh file reference_images identik sebelum/sesudah upgrade. users=1, auth_sessions=1,
audit_events=5; tabel katalog/cleanup tetap kosong, ketiga tabel baru kosong, file foto=0.
Tidak menjalankan seed/login/mutasi domain di development. Rincian ada di laporan 1B-01.

Pada 19 Oktober 2026, Task 1B-02 memperbarui runtime API/web tanpa migration baru.
Alembic current tetap 0004 dan check tanpa operasi baru. Fingerprint seluruh 11 tabel
aplikasi, alembic_version, spatial_ref_sys dan file storage identik sebelum/sesudah;
tidak melakukan login/seed/mutasi pada development. Database container/volume existing
dipertahankan. Rincian pengujian CRUD/RBAC dan smoke ada di laporan 1B-02.

## Receipt CSV — Task 1B-03

Revision 0005_asset_imports menambah asset_import_batches tanpa mengubah tabel/domain existing:
id UUID PK (idempotency key), actor_id FK users RESTRICT/index, request_sha256 varchar(64)
dengan CHECK panjang 64, result_json JSONB (SQLite JSON), created_at timestamp server.
Receipt sukses disimpan dalam transaksi batch bersama aset/identifier/asset_change_events.
Placeholder internal tidak pernah committed; kegagalan me-rollback semuanya. Preview tidak
membuat receipt. Tidak menyimpan CSV mentah; result menyimpan row/asset/version dan hint staging.
Tidak ada lokasi aktif, tabel AI, cache proses atau pruning receipt otomatis.

Deploy: build API/migrate/web → migrate upgrade head → recreate API/web saja. Readiness wajib
0005 dan ledger. Downgrade 0005 hanya menghapus receipt/hint dan kemampuan replay key lama,
tidak menghapus aset/identifier/audit yang telah dibuat. Hanya diuji pada DB sementara;
jangan downgrade operasional tanpa backup karena kehilangan jaminan retry receipt.

Pada 19 Oktober 2026, development di-upgrade 0004→0005 dan API/web diperbarui tanpa
mengganti database container/volume. Alembic current/check lulus. Fingerprint seluruh 11
tabel aplikasi existing, spatial_ref_sys dan file foto identik sebelum/sesudah; hanya
revision berubah dan ledger baru kosong. Tidak melakukan login/seed/import/mutasi domain
di development. Laporan dan hasil regresi/smoke ada di SPRINT_1B_03_REPORT.md.

## Pengujian dan backup existing

Task 1A-05 tidak menambah atau mengubah schema/migration. Audit tetap pada audit_events;
catalog_create/update/archive merekam table/id/version dan reference_image_upload/delete
merekam model_id/image_id/version (version model sesudah mutasi), actor_id dan created_at.
Detail audit sengaja tidak memuat body input, cookie/token, path storage, atau foto.
Pengujian rollback audit melindungi transaksi create/update/archive/upload/delete.
Tidak ada hard-delete model/master atau endpoint edit/delete audit.

Smoke katalog menggunakan db-test tmpfs dan direktori foto tmpfs milik api-smoke uid 10001,
tanpa mount postgres_data/reference_images. Guard pada smoke memeriksa backend PostgreSQL,
host db-test, nama assetvision_test, dan user test_runner sebelum menulis fixture akun.

compose.test.yaml menyediakan database assetvision_test di container db-test dengan tmpfs.
Fixture memvalidasi nama database sebelum menghapus tabel. Pengujian menjalankan migrasi yang sama,
kemudian roundtrip downgrade/upgrade dan pemeriksaan metadata. SQLite in-memory hanya untuk pengujian cepat.

Backup lokal dapat dibuat dari Ubuntu dengan perintah berikut; folder data/backups diabaikan Git:

```bash
mkdir -p data/backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > data/backups/assetvision.dump
```

Simpan backup dengan akses terbatas; berisi email dan hash password. Pemulihan membutuhkan
prosedur eksplisit sesuai target database, tidak dilakukan otomatis oleh aplikasi.

## Migration 0007_asset_location — Task 2-02

assets mendapat current_location_id UUID nullable dengan FK locations.id (NO ACTION,
tanpa cascade, index) dan location_verified_at timestamptz nullable. Existing version tidak
diubah saat upgrade; tidak ada backfill, seed atau penafsiran location_hint. SQLite memakai
nullable ADD COLUMN REFERENCES tanpa rebuild tabel aset yang sudah direferensikan; FK default
NO ACTION juga dipakai PostgreSQL agar reflection Alembic konsisten. DELETE lokasi sudah
dilarang guard 0006. Event asset_events: UUID PK, asset_id/actor_id FK RESTRICT, event_type,
occurred_at, recorded_at, payload_json JSON/JSONB, correlation_id UUID unique; index asset/waktu.
History guard menolak rewrite/delete. Initial placement saja yang menulis pada task ini.

Downgrade ke 0006 menolak bila ada event atau lokasi/timestamp resmi non-null. Roundtrip
hanya diuji pada database test. Tidak mengubah migration 0001–0006. Readiness mensyaratkan
head 0007 dan dapat membaca seluruh kolom aset serta asset_events.

## Migration 0008_asset_movements — Task 2-03

Tabel asset_movements baru: UUID PK, asset_id FK RESTRICT, from_location_id FK nullable,
to_location_id FK wajib, status PENDING/APPROVED/REJECTED/CANCELLED, reason,
requested_by/at, expected_asset_version, request_snapshot_json JSON/JSONB, reviewed_by/at,
review_reason, approved_at, effective_at dan optimistic version. Index asset_id/status/
requested_at. Semua actor/location FKs tanpa cascade. Expected asset version positif dan
lebih kecil dari batas int32; movement version mulai 1 dan menjadi 2 pada satu keputusan.

Check constraints mengikat null/non-null review/approval dengan status, alasan canonical
nonblank 1–2000 karakter dan tujuan berbeda dari asal. Trigger di PostgreSQL/SQLite menolak
insert terminal, perubahan field request, transisi di luar PENDING → terminal, increment
version tidak sesuai, rewrite terminal, dan DELETE. Event memakai tabel asset_events dan
history guard 0007 existing; tidak mengubah snapshot/event lama. Tidak ada trigger yang
menggantikan autentikasi atau mencatat audit untuk penulis SQL eksternal.

Upgrade 0008 tidak UPDATE tabel existing/backfill/seed, hanya menambah tabel kosong. Migration
0001–0007 tidak diubah. Downgrade ke 0007 hanya jika asset_movements kosong; bila berisi
request historis ditolak sebelum DROP, apa pun statusnya. Roundtrip hanya pada database test.

## Migration 0009_observations — Task 2-04

Tabel location_observations baru menyimpan UUID PK, asset_id nullable FK RESTRICT,
observed_location_id/observed_by wajib FK, observed_at/recorded_at timestamptz, evidence_note,
official_location_id_at_recording nullable FK, asset_version_at_recording nullable,
comparison_status, snapshot_json JSONB, review_status, reviewed_by/at/review_reason nullable,
dan optimistic version. Semua FK tanpa cascade. Index latest(asset_id,observed_at,recorded_at,id),
observed_at dan review_status mendukung history/inbox/status. Tidak mengubah tabel existing.

Checks mengikat asset/version/comparison, lokasi match/conflict, note/reason bounded canonical,
serta null/non-null kolom review. Trigger PostgreSQL/SQLite memastikan insert PENDING/version1,
evidence immutable, hanya satu transisi ACKNOWLEDGED/DISMISSED dengan version+1, terminal
immutable dan DELETE ditolak. Aplikasi wajib menulis linked asset_events atau unlinked
AuditEvent dalam transaksi sama; trigger bukan pengganti RBAC/audit bagi SQL owner eksternal.

Upgrade tidak backfill/seed/UPDATE data lama. Migration 0001–0008 tidak diubah. Downgrade
ke 0008 menolak sebelum DROP bila ada observasi, termasuk dismissed. Roundtrip kosong,
upgrade populated predecessor dan penolakan populated downgrade diuji hanya di database test.
Readiness memeriksa head 0009 dan tabel baru. Timeline membaca sumber lama tanpa duplikasi.

## Frontend Task 2-05

Tidak ada migration, perubahan tabel/trigger, pemetaan hint atau seed development pada task
frontend ini. Head tetap 0009_observations. UAT/smoke memakai db-test/assetvision_test tmpfs,
terpisah dari DB/storage development. Fixture browser dibuat eksplisit lewat runner test,
dengan akun acak test saja; tidak membuat role/akun development. Fingerprint seluruh data
existing dan storage dibandingkan sebelum/sesudah pembaruan web. Bukti final di laporan 2-05.


## Task 3-02 — Versioned embedding index

Head0010_embedding_index menambah embedding_indexes, image_embeddings dan embedding_index_state.
Encoder name/version/full weight SHA/preprocess/dimensions berada di encoder_spec JSONB parent;
setiap vector menunjuk generation FK. Reference SHA, snapshot UUID dan model UUID dipertahankan.
FK current reference ON DELETE SET NULL kompatibel dengan delete foto existing; history tidak
cascade. Unique(index_id,reference_snapshot_id), source/capacity insert guards, immutable history
UPDATE/DELETE dan head CAS version guards diuji SQLite/PostgreSQL. Vector shape/L2/finiteness
juga divalidasi service/reader. Tidak mengubah kolom existing atau menambah pgvector.

Migration hanya membuat tabel baru dan head(id1,current_index_id=null,version1), tanpa encoder,
vector, audit, seed atau hint mapping. Populated downgrade ditolak. Data existing selain revisi
Alembic harus identik sebelum/sesudah. Rebuild adalah operasi ADMIN terpisah, bukan migration.


## Migration0011_recognition_surveys — Task 3-05

recognition_jobs, survey_observations, recognition_reviews additive, kosong saat upgrade.
FK references users/model/assets/location/job/observation, review unik per observation,
request UUID unik/digest untuk retry; seluruh evidence/review immutable via triggerUPDATE/DELETE.
Review linkage pada selected_asset_id nullable, tidak overwrite prediction/master. JSONB diPG,
JSON diSQLite. Downgrade menolak bila salah satu tabel berisi data. Head/readiness0011.
Tidak UPDATE/backfill/seed tabel existing; storage cleanup melindungi reference dan job key.
