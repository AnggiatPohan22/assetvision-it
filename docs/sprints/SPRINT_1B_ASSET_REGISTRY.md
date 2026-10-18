# AssetVision IT — Sprint 1B: Physical Asset Registry

**Status:** Planned · **Prasyarat:** Sprint 1A selesai · **Estimasi:** 6–9 hari kerja · **Prioritas:** P0

## Tujuan

Membangun daftar **unit fisik aset** terpisah dari katalog model. Satu model Ruijie AP680-L dapat memiliki delapan Asset ID berbeda, dengan SN/MAC masing-masing; SN boleh kosong/rusak. Lokasi dan mutasi formal baru menjadi domain Sprint 2.

## Lingkup

**Termasuk:** Asset ID permanen, relasi ke model, identifier SN/MAC/hostname/management ID, status lifecycle, kondisi perangkat, catatan, tanggal pembelian/pemasangan opsional, pencarian/filter, import CSV preview/validasi, export CSV, foto unit opsional, audit perubahan metadata, UI, tests.

**Tidak termasuk:** movement approval, location history, OCR, pengenalan foto, rekonsiliasi controller, dan AI. Untuk lokasi sementara, **jangan membuat kolom string `current_location` bebas**; tunggu FK `locations` Sprint 2 atau gunakan field staging import yang tidak dianggap authoritative.

## Invariant bisnis

- `asset_code` immutable, unik, tidak pernah didaur ulang; contoh `AP-001`.
- Setiap asset menunjuk satu `device_model_id` yang valid; model tidak boleh dihapus ketika masih direferensikan.
- SN bisa null karena stiker rusak. Jangan gunakan placeholder palsu seperti `UNKNOWN` sebagai SN.
- MAC harus dinormalisasi (`AA:BB:CC:DD:EE:FF`) dan divalidasi; satu perangkat dapat punya banyak MAC berbeda jenis (LAN/WLAN/BSSID), tidak semua MAC bersifat unik global untuk semua konteks.
- Identitas yang diklaim harus punya tipe, nilai, sumber (`MANUAL`, `IMPORT`, `CONTROLLER`, dll), dan status verifikasi.
- Perubahan metadata penting dicatat dengan aktor, waktu, old/new value; tidak mengubah `asset_code`.
- Tidak ada public registration; ADMIN dapat mengelola, OFFICER read; role lainnya mengikuti kebijakan Sprint 0.

## Skema inti

| Entitas | Kolom inti | Catatan |
|---|---|---|
| `assets` | id UUID, asset_code unique, device_model_id FK, lifecycle_status, condition, notes, purchase_date nullable, installed_at nullable, created_at, updated_at, version int | `asset_code` immutable; `version` untuk optimistic concurrency |
| `asset_identifiers` | id UUID, asset_id FK, identifier_type, normalized_value nullable, raw_value nullable, verification_status, source, notes, created_at | nullable jika bukti label rusak dicatat di status asset/observasi; bukan baris identifier kosong |
| `asset_photos` (opsional) | id UUID, asset_id FK, storage_key, mime_type, sha256, uploaded_at | gunakan storage provider Sprint 1A |
| `asset_change_events` | id UUID, asset_id FK, actor_id FK, event_type, before_json, after_json, recorded_at | audit metadata, jangan menggantikan movement log Sprint 2 |

**Constraint:** unique `asset_code`; unique identifier berdasarkan `(identifier_type, normalized_value)` **hanya untuk tipe yang secara bisnis dipastikan unik**, misalnya serial per manufacturer setelah disambiguasi; untuk MAC/BSSID, rancang scope/tipe secara eksplisit dan laporkan collision, jangan menerapkan unique global secara buta. Index asset_code, model_id, identifier lookup.

## API minimum

| Method | Route | Role |
|---|---|---|
| GET | `/assets?search=&model_id=&status=&page=&page_size=` | authenticated |
| POST | `/assets` | ADMIN |
| GET | `/assets/{id}` | authenticated |
| PATCH | `/assets/{id}` | ADMIN; dilarang ubah asset_code |
| POST | `/assets/{id}/archive` | ADMIN |
| GET/POST | `/assets/{id}/identifiers` | read authenticated / write ADMIN |
| PATCH/DELETE | `/assets/{id}/identifiers/{identifier_id}` | ADMIN, soft-delete/audit |
| POST | `/assets/imports/preview` | ADMIN |
| POST | `/assets/imports/commit` | ADMIN |
| GET | `/assets/export.csv` | ADMIN (atau role yang disetujui) |

**CSV:** wajib `asset_code`, `manufacturer`, `model`; optional `serial_number`, `mac_address`, `hostname`, `condition`, `status`, `notes`, `location_hint`. Preview harus menunjukkan baris valid, invalid, duplikat internal CSV, benturan database, dan model tidak dikenal. Commit menggunakan import id/token atau payload tervalidasi ulang, idempotency key, transaksi per batch dengan laporan sukses/gagal yang jelas. Jangan otomatis membuat model baru tanpa approval. Sanitasi nilai ekspor CSV untuk mencegah formula injection.

## UI minimum

- Daftar aset dengan filter, search Asset ID/SN/MAC, pagination.
- Form tambah/edit unit memilih model dari katalog Sprint 1A.
- Detail aset: identifier list, foto, metadata, audit perubahan.
- Import CSV: upload → preview errors → confirm → summary.
- Badge label SN rusak/tidak tersedia **tanpa** membuat SN palsu.

## Task Codex berurutan

1. **1B-01 Schema + invariants:** assets, identifiers, audit metadata, migration, constraints, tests.
2. **1B-02 CRUD API + RBAC:** create/list/detail/update/archive, immutable code, optimistic version.
3. **1B-03 CSV:** preview/commit/export, idempotency, duplicate handling, tests.
4. **1B-04 Frontend:** list/detail/form/import, validations.
5. **1B-05 Hardening:** audit, docs, regression Sprint 0/1A, seed 8 AP sintetis.

## Acceptance criteria

- [ ] Satu model Ruijie AP680-L memiliki tepat 8 unit contoh berbeda (`AP-001`…`AP-008`).
- [ ] `AP-001` SN `123456789`, `AP-002` SN `2158763`; sisanya data sintetis, bukan data produksi.
- [ ] Asset code tidak dapat diubah lewat API atau import.
- [ ] Unit dengan SN kosong tetap dapat dibuat.
- [ ] Pencarian Asset ID, SN, MAC mengembalikan unit yang benar.
- [ ] Identifier duplicate/collision ditangani jelas, tidak ditimpa diam-diam.
- [ ] CSV preview tidak mengubah database; commit terotorisasi dan idempotent.
- [ ] User non-ADMIN tidak dapat mengubah master asset.
- [ ] Event audit tercatat untuk create/update/archive/identifier change.
- [ ] Tests migrasi, API, CSV, RBAC, UI lulus.

## Handoff ke Sprint 2

Pastikan `assets.id` dan `asset_code` stabil; semua lokasi impor masih berupa `location_hint` staging, **belum** lokasi aktif. Sprint 2 akan menambahkan `current_location_id` dan mekanisme mutasi resmi.

## Kontrak kerja dengan Codex

1. Baca `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/BUSINESS_RULES.md`, dan migration yang sudah ada sebelum mengubah kode. **Repository adalah sumber kebenaran implementasi**; dokumen ini adalah spesifikasi target, bukan klaim fitur sudah tersedia.
2. Inspeksi struktur, dependensi, API, autentikasi/RBAC, pola testing, dan keadaan Git; rangkum gap terhadap sprint.
3. Buat rencana implementasi singkat, lalu kerjakan **satu task terbatasi per iterasi**. Jangan mengerjakan sprint berikutnya.
4. Pertahankan backward compatibility bila memungkinkan; setiap perubahan skema wajib migration Alembic yang reversible bila aman. Jangan mengedit migration yang sudah diterapkan.
5. Gunakan validasi Pydantic, SQLAlchemy, dependency RBAC server-side, transaksi database, dan test positif/negatif. Jangan menaruh secret, foto aset asli, atau database dump di Git.
6. Setelah task selesai, laporkan file yang berubah, perintah yang benar-benar dijalankan, hasil test nyata, risiko, dan langkah manual yang tersisa. Jangan mengklaim test lulus bila tidak dijalankan.
7. Jika detail implementasi Sprint 0 berbeda dari asumsi dokumen, **adaptasikan ke pola yang sudah ada**, jelaskan trade-off, dan jangan membangun sistem paralel.

## Perintah validasi umum (sesuaikan dengan repository)

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose exec api alembic upgrade head
docker compose exec api pytest -q
# Jika frontend container memuat tooling development:
docker compose exec web npm run lint
docker compose exec web npx tsc --noEmit
```

> Jika image runtime tidak menyertakan pytest/npm development tooling, gunakan mekanisme test lokal atau service test yang sudah disediakan repository. Pastikan hasilnya dicatat.

## Prompt pembuka untuk chat baru / Codex

```text
Implementasikan AssetVision IT Sprint 1B berdasarkan docs/sprints/SPRINT_1B_ASSET_REGISTRY.md. Inspeksi implementasi Sprint 0/1A, AGENTS.md, migration, dan test. Kerjakan task 1B-01 saja: schema, invariants asset_code/identifiers, audit model, migration, dan tests. Jangan membuat modul lokasi/movement atau AI. Laporkan diff dan hasil validasi; tunggu approval untuk task berikutnya.
```
