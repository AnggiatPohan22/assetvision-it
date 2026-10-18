# AssetVision IT — Sprint 1A: Device Model Catalog

**Status:** Planned · **Prasyarat:** Sprint 0 selesai dan lolos acceptance · **Estimasi:** 5–8 hari kerja · **Prioritas:** P0

## Tujuan

Membangun **master katalog jenis/model perangkat** yang dikelola IT Admin. Katalog merepresentasikan *model*, **bukan unit fisik**. Contoh: Ruijie AP680-L dibuat sekali sebagai model; delapan unit fisiknya baru dibuat di Sprint 1B.

## Lingkup

**Termasuk:** kategori perangkat, manufacturer, model, alias/nama alternatif, deskripsi, spesifikasi JSON terbatas, environment indoor/outdoor/both, status aktif/nonaktif, foto referensi, pencarian/filter, pagination, validasi, audit dasar, dokumentasi, seed data sintetis, dan automated tests.

**Tidak termasuk:** unit aset/SN, lokasi operasional, perpindahan, OCR, AI embedding, pengenalan kamera, upload ke cloud, dan training model.

## Invariant bisnis

- `DeviceModel` tidak pernah disamakan dengan `Asset`.
- Satu pasangan `(manufacturer, normalized_model_name)` unik secara case-insensitive; alias dapat menampung ejaan lain.
- Kategori/model yang sudah direferensikan tidak dihapus secara fisik; gunakan `is_active=false` atau soft-delete sesuai pola repository.
- Foto referensi tidak membuktikan identitas unik unit fisik.
- Hanya ADMIN dapat create/update/archive; OFFICER/VIEWER hanya read sesuai RBAC.
- Metadata foto dan lokasi file disimpan terpisah; **path absolut host tidak dikirim ke client**.

## Rancangan data (sesuaikan naming existing)

| Entitas | Kolom inti | Constraint / catatan |
|---|---|---|
| `device_categories` | id UUID, code, name, description, is_active, timestamps | `code` unique |
| `manufacturers` | id UUID, name, normalized_name, website nullable, is_active | normalized_name unique |
| `device_models` | id UUID, manufacturer_id FK, category_id FK, model_name, normalized_model_name, aliases JSONB, description, environment, specs JSONB, is_active, timestamps | unique(manufacturer_id, normalized_model_name); enum environment |
| `device_reference_images` | id UUID, device_model_id FK, storage_key, sha256, mime_type, byte_size, angle nullable, is_primary, uploaded_by FK, created_at | hanya metadata; gambar tersimpan lokal |

**Index:** manufacturer/category/model; pagination dengan urutan deterministik. JSON specs bukan pengganti kolom yang memerlukan constraint. Tambahkan `created_by/updated_by` bila pola audit Sprint 0 tersedia.

## Kontrak API yang diusulkan

Semua endpoint di bawah `/api/v1`, menggunakan auth Sprint 0 dan response/error schema konsisten.

| Method | Route | Role |
|---|---|---|
| GET | `/device-categories` | semua authenticated |
| POST/PATCH | `/device-categories`, `/device-categories/{id}` | ADMIN |
| GET | `/manufacturers` | semua authenticated |
| POST/PATCH | `/manufacturers`, `/manufacturers/{id}` | ADMIN |
| GET | `/device-models?search=&category_id=&manufacturer_id=&page=&page_size=` | semua authenticated |
| POST | `/device-models` | ADMIN |
| GET/PATCH | `/device-models/{id}` | read semua / write ADMIN |
| POST | `/device-models/{id}/archive` | ADMIN |
| POST | `/device-models/{id}/reference-images` | ADMIN |
| GET | `/device-models/{id}/reference-images` | semua authenticated |
| DELETE | `/device-models/{id}/reference-images/{image_id}` | ADMIN |

**Upload:** multipart; JPEG/PNG/WebP saja; default maksimum 8 MB/file; cek magic bytes, decode gambar, ukuran dimensi, dan batas pixel; buat nama acak, hitung hash, buang EXIF GPS bila tidak diperlukan. Batasi jumlah foto per model secara configurable. Unduhan lewat endpoint terautentikasi atau URL bertanda tangan internal, bukan path filesystem mentah. Storage abstraction `StorageProvider` dengan `LocalStorageProvider` sebagai implementasi awal. Penanganan orphan file jika transaksi DB gagal.

## UI minimum

- `/catalog/models`: tabel model, filter kategori/manufacturer, search, status.
- `/catalog/models/new`: form tambah model.
- `/catalog/models/[id]`: detail, galeri foto, edit, archive.
- Pengelolaan kategori/manufacturer minimal melalui halaman admin atau dialog.
- State loading/empty/error, validasi form, aksesibilitas dasar, mobile responsive.

## Task Codex berurutan

1. **1A-01 Schema:** models, migration, constraints, indexes, seed kategori/manufacturer sintetis.
2. **1A-02 CRUD API:** list/detail/create/update/archive, filtering, RBAC, error contract, tests.
3. **1A-03 Image storage:** provider interface, upload/serve/delete, validasi file, tests.
4. **1A-04 Frontend:** list/filter, create/edit/detail, galeri, permission-aware UI.
5. **1A-05 Hardening:** audit events, pagination, docs/OpenAPI, end-to-end smoke test.

## Acceptance criteria

- [ ] ADMIN bisa membuat kategori/manufacturer/model `Ruijie AP680-L` satu kali.
- [ ] Model dengan nama sama (beda kapital/spasi) pada manufacturer sama ditolak 409/422 sesuai kontrak.
- [ ] Model sama dari manufacturer berbeda boleh jika memang valid.
- [ ] ADMIN dapat mengunggah ≥5 foto referensi model dan melihatnya kembali.
- [ ] File tidak valid/terlalu besar ditolak tanpa meninggalkan file orphan.
- [ ] OFFICER/VIEWER tidak bisa membuat, mengedit, archive, atau upload (403).
- [ ] Archive tidak menghapus referensi historis.
- [ ] Filter, pagination, empty state, dan mobile layout berfungsi.
- [ ] Migration dan tests backend/frontend yang relevan lulus.

## Dataset uji

- Kategori: Access Point, Router, Switch, CCTV, Printer.
- Manufacturer: Ruijie, Ubiquiti, MikroTik.
- Model: Ruijie AP680-L (outdoor), dua model AP mirip, satu router.
- Gunakan foto sintetis/dummy yang boleh disimpan di repo; foto perusahaan sebenarnya di storage lokal terabaikan Git.

## Handoff ke Sprint 1B

Pastikan `device_models.id` stabil, API list/detail siap dipakai oleh form asset, dan referensi foto dapat dibaca melalui authorization. Catat nama tabel dan kontrak aktual di `docs/DATABASE.md` dan `docs/API_CONTRACT.md`.

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
Implementasikan AssetVision IT Sprint 1A berdasarkan docs/sprints/SPRINT_1A_DEVICE_CATALOG.md.
Baca AGENTS.md dan inspeksi hasil Sprint 0 dahulu. Kerjakan task 1A-01 saja: schema SQLAlchemy, migration Alembic, constraints, dan tests. Jangan mengerjakan Sprint 1B atau AI. Setelah selesai, laporkan diff, perintah, hasil test, dan instruksi review. Tunggu approval sebelum 1A-02.
```
