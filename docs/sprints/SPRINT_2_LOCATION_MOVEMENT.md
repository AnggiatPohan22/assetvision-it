# AssetVision IT — Sprint 2: Location, Movement & Audit Trail

**Status:** In progress — Task 2-01–2-04 diimplementasikan; 2-05 belum dimulai · **Prasyarat:** Sprint 1B selesai · **Estimasi:** 8–12 hari kerja · **Prioritas:** P0

Task 2-01 menambah hierarki, tree API adjacency, API ADMIN create/PATCH/archive,
cycle guards aplikasi/database, version, audit dan migration 0006. Tidak menambah
FK lokasi aset, placement, movement, timeline/observasi atau UI lokasi. Floorplan/pin
opsional ditunda. Hasil eksekusi dan preservasi: `SPRINT_2_01_REPORT.md`.
Task 2-02 menambah FK nullable, penempatan awal ADMIN/event atomik dan lookup lokasi;
tanpa pemetaan hint atau penempatan development. Hasil: `SPRINT_2_02_REPORT.md`.
Task 2-03 menambah movement request/approve/reject/cancel, RBAC, version/atomic event,
API history/inbox dan tests. Self-approval ADMIN diizinkan untuk pilot dan dicatat eksplisit.
Hasil: `SPRINT_2_03_REPORT.md`.
Task 2-04 menambah timeline gabungan read-only, observasi/review dan proyeksi location conflict
tanpa mengubah master aset. Hasil: `SPRINT_2_04_REPORT.md`. UI/UAT Task 2-05 belum dimulai.

## Tujuan

Menyediakan **lokasi authoritative saat ini**, hierarki lokasi indoor/outdoor, **riwayat perpindahan yang tidak hilang**, approval oleh ADMIN, serta observasi audit lokasi. Kasus utama: AP-003 pindah dari Villa 1 ke Villa 10; lokasi aktif berubah hanya setelah approval, histori tetap tersimpan.

## Lingkup

**Termasuk:** site/area/building/floor/room/spot, koordinat outdoor opsional, titik denah indoor opsional, lokasi terakhir diverifikasi, request movement, approval/reject, event timeline, location conflict, optimistic concurrency, UI dan tests.

**Tidak termasuk:** AI pengenalan gambar, OCR, geocoding berbayar, peta interaktif kompleks, tracking GPS terus-menerus, controller network. Upload floorplan dapat ditunda jika tidak menghambat acceptance inti.

## Invariant bisnis

- `assets.current_location_id` adalah **lokasi resmi terakhir**; bukan otomatis lokasi aktual fisik.
- `observed_location_id` dari survei/audit adalah **bukti**, tidak langsung menimpa lokasi resmi.
- Setiap movement menyimpan from, to, requester, approver, reason, `requested_at`, `approved_at`, `effective_at`, dan status.
- Hanya approval berotorisasi yang mengubah lokasi aktif; perubahan dilakukan dalam **satu transaksi** bersama event.
- Movement yang ditolak/dibatalkan tidak mengubah lokasi aktif.
- Request stale (asset sudah dipindah pihak lain) harus ditolak konflik 409 dan diperiksa ulang.
- Event history append-only secara aplikasi; koreksi melalui event baru, bukan menghapus event lama.
- Lokasi indoor dapat menggunakan hierarchy + floorplan coordinates, **bukan GPS presisi ruangan**.
- GPS outdoor menyimpan accuracy dan timestamp jika tersedia; GPS tidak dianggap bukti identitas unik.

## Rancangan skema

| Entitas | Kolom inti | Catatan |
|---|---|---|
| `locations` | id UUID, parent_id self FK, code, name, kind, is_active, latitude nullable, longitude nullable, gps_accuracy_m nullable, floorplan_id nullable, pin_x nullable, pin_y nullable | `kind`: SITE, BUILDING, FLOOR, ROOM, AREA, SPOT; validasi no cycles |
| `assets` (migration) | current_location_id FK nullable, location_verified_at nullable, version int | null jika belum ditempatkan; increment version on approved move |
| `asset_movements` | id UUID, asset_id FK, from_location_id FK nullable, to_location_id FK, status, reason, requested_by, reviewed_by nullable, requested_at, reviewed_at nullable, effective_at nullable, expected_asset_version | state machine PENDING → APPROVED/REJECTED/CANCELLED |
| `asset_events` | id UUID, asset_id FK, event_type, actor_id, occurred_at, recorded_at, payload_json, correlation_id | append-only event timeline |
| `location_observations` | id UUID, asset_id FK nullable, observed_location_id FK, observed_by, observed_at, evidence_note, review_status | bukti lapangan, bukan update otomatis |
| `floorplans` (opsional) | id UUID, location_id FK, storage_key, width_px, height_px | pin normalized x/y 0..1 |

**Data migration:** lakukan backfill `location_hint` Sprint 1B hanya setelah admin memetakan ke `locations.id`; jangan tebak lokasi dari teks secara diam-diam. Hindari circular parent_id, constraint pin 0..1, unique code per parent, index current_location_id/status/timestamp. Bila lokasi lama diarsipkan, histori tetap terbaca.

## Workflow movement

```text
OFFICER/ADMIN membuat movement request
  → server menyimpan from_location_id + asset_version saat request
  → ADMIN review
      → REJECT: simpan keputusan, lokasi tidak berubah
      → APPROVE: lock asset row / compare version
          → jika stale: 409 CONFLICT, perlu review ulang
          → jika valid: update assets.current_location_id
                     + append asset_movement APPROVED
                     + append asset_event
                     + increment version
          → commit atomik
```

ADMIN tidak boleh mengubah lokasi lewat PATCH asset umum; semua perubahan resmi melalui movement workflow (termasuk initial placement yang perlu event tersendiri). Kebijakan self-approval dapat dilarang untuk kontrol internal atau diizinkan pada pilot dengan pencatatan jelas; pilih dan dokumentasikan satu kebijakan.

## API minimum

| Method | Route | Role |
|---|---|---|
| GET | `/locations?parent_id=&kind=&search=` | authenticated |
| POST/PATCH | `/locations`, `/locations/{id}` | ADMIN |
| GET | `/assets/{id}/timeline` | authenticated |
| GET | `/assets/{id}/movements` | authenticated |
| POST | `/assets/{id}/movements` | OFFICER/ADMIN |
| POST | `/movements/{id}/approve` | ADMIN |
| POST | `/movements/{id}/reject` | ADMIN |
| GET | `/movements?status=PENDING` | ADMIN |
| POST | `/location-observations` | OFFICER/ADMIN |
| GET | `/location-observations?review_status=` | ADMIN |

## UI minimum

- Location tree (site → area/building → floor/room/spot), create/edit/archive ADMIN.
- Detail aset menampilkan lokasi resmi, waktu verifikasi, dan timeline.
- Form movement request (asal otomatis, tujuan dipilih, alasan).
- Approval inbox untuk ADMIN dengan perbandingan lokasi dan histori.
- Badge `LOCATION_CONFLICT` jika observasi tidak cocok; tidak otomatis memindahkan.
- Mobile-friendly, loading/error/conflict states.

## Task Codex berurutan

1. **2-01 Location hierarchy:** schema, migration, tree API, cycle prevention, tests.
2. **2-02 Asset location:** FK, initial placement event, location lookup, tests.
3. **2-03 Movement state machine:** request/approve/reject, transactions, concurrency, RBAC, tests.
4. **2-04 Timeline & observations:** append-only events, location conflict, API, tests.
5. **2-05 Frontend & UAT:** location tree, movement inbox, asset timeline, docs.

## Acceptance criteria

- [x] Lokasi Lounge, Lobby, Villa 1, Villa 10 dapat dibuat dalam hierarki (fixture sintetis API/smoke, bukan seed development).
- [x] AP-003 ditempatkan di Villa 1 melalui event yang tercatat (fixture/smoke sintetis, bukan development).
- [x] OFFICER mengajukan mutasi Villa 1 → Villa 10; sebelum approval lokasi resmi tetap Villa 1.
- [x] ADMIN approve → lokasi resmi Villa 10 dan event histori mencatat asal/tujuan/aktor/waktu.
- [x] Reject → tidak ada perubahan lokasi.
- [x] Approval ganda/stale menghasilkan konflik, tidak ada lost update.
- [x] Observasi AP-003 di Villa 1 setelah pindah ke Villa 10 menimbulkan conflict, bukan auto-revert.
- [x] Cycle lokasi (parent menjadi descendant) ditolak (API/SQL langsung dan race PostgreSQL).
- [x] Non-ADMIN tidak bisa approve/reject.
- [x] Event historis tetap ada setelah lokasi diarsipkan.
- [ ] Migration, RBAC, concurrency, dan UI tests lulus.

## Handoff ke Sprint 3

Recognition engine dapat menggunakan `assets.current_location_id` sebagai **bukti pendukung**, ditambah movement history dan observation recency. **Lokasi tidak boleh digunakan sebagai bukti tunggal untuk VERIFIED.**

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
Implementasikan AssetVision IT Sprint 2 berdasarkan docs/sprints/SPRINT_2_LOCATION_MOVEMENT.md. Baca AGENTS.md, skema Asset Registry, dan migration existing. Kerjakan task 2-01 saja: location hierarchy, constraint no cycles, migration, API dan tests. Jangan implementasi AI/OCR. Tunjukkan diff, hasil test, serta dampak migration; tunggu approval untuk 2-02.
```
