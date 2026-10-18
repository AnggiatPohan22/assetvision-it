# Database

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

## Pengujian dan backup

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
