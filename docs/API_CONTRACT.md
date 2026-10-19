# API Contract

## Task 2-01 — Location hierarchy

Semua path di bawah `/api/v1`, memakai cookie/session dan CSRF existing.

| Method | Path | Hak akses / hasil |
|---|---|---|
| GET | `/locations` | authenticated, page berisi items/total/page/page_size/total_pages |
| GET | `/locations/tree` | authenticated, adjacency `{items: Location[], total}` termasuk arsip |
| GET | `/locations/{uuid}` | authenticated, detail atau 404 |
| POST | `/locations` | ADMIN, 201 |
| PATCH | `/locations/{uuid}` | ADMIN, 200 dengan version baru |

List: `parent_id` untuk direct children; tanpa parent_id membaca semua lokasi, `roots_only=true`
untuk root (tidak boleh bersama parent_id). Filter `kind`, `is_active`, `search` name/code
case-insensitive dan literal wildcard; page default 1, maksimum 1 juta; page_size default 20,
1–100. Urutan code lalu UUID. Tree urutan sama, flat adjacency lengkap maksimal 5000 node;
lebih dari batas menghasilkan 409, tidak mengembalikan tree terpotong. Archive tetap terbaca.
Pagination offset bukan snapshot lintas request. Unknown query fields ditolak 422.

Create wajib code/name/kind. Opsional parent_id null (root), is_active default true,
latitude/longitude, gps_accuracy_m, gps_recorded_at ISO8601 berzona. Kind uppercase
SITE/BUILDING/FLOOR/ROOM/AREA/SPOT. PATCH wajib `version` dan minimal satu perubahan;
hasil gabungan koordinat diperiksa. Null hanya untuk parent/koordinat/akurasi/waktu.
Server owns UUID/actor/timestamp/version awal; extra fields termasuk floorplan/pin ditolak.
Arsip/restore via PATCH is_active; tidak ada hard DELETE/endpoint archive terpisah.

409: stale version, cycle, kode sibling/root duplikat (termasuk archived), parent archived.
422: validasi/parent tak dikenal; 401 anonim/inactive/revoked; 403 role/Origin/CSRF.
Mutasi JSON maksimal 16 KiB streaming di API dan proxy (413); non-JSON 415.
Semua response private/no-store/nosniff. Audit location_create/update/archive menyimpan
actor, timestamp, UUID serta snapshot before/after JSON string dalam details existing.
Tidak ada placement, asset location lookup, movement, timeline atau observation API pada 2-01.

## Hardening 1B-05

Kontrak endpoint, cookie/CSRF/RBAC dan version tetap sama; tidak menambah API seed/reset.
Seed sintetis adalah CLI dengan ADMIN actor, explicit confirmation dan transaction; lihat
README/DATABASE. Semua audit domain tetap atomik. Rantai before/after version serta private
error rollback diuji kembali; tidak membuka SQL/exception/request body pada respons 500.
Client menganggap sukses dengan JSON tidak terbaca/non-object sebagai hasil belum pasti,
bukan bukti berhasil atau izin retry create otomatis. Impor mempertahankan key/payload
yang sama dan memberi peringatan unload best-effort selama hasil belum diketahui.

## Riwayat unit untuk UI — Task 1B-04

`GET /api/v1/assets/{asset_id}/events?page=1&page_size=10` tersedia untuk semua role
terautentikasi yang dapat membaca unit. Unit tidak ada → 404; anonim → 401.
Query hanya page (1–1.000.000) dan page_size (1–100), unknown query → 422.
Response Page memuat items/total/page/page_size/total_pages. Item berisi id, asset_id,
actor_id (UUID, tanpa email/password/session), event_type, recorded_at, before_json nullable,
after_json. Snapshot berasal dari transaksi audit existing. Urutan recorded_at desc,
version asset pada after_json desc untuk timestamp sama, lalu UUID desc.
Offset pagination bukan snapshot antar-request bila ada writer baru. Tidak tersedia
POST/PATCH/DELETE event; proxy hanya mengizinkan GET. Tidak mengubah kontrak CRUD/CSV.

UI `/assets/import` mengirim JSON csv_text dari file UTF-8, bukan multipart. Preview dan
collision acknowledgement dilakukan sebelum konfirmasi. Retry setelah hasil tidak pasti
menggunakan CSV/idempotency_key/flag persis sama dalam state halaman; navigasi/reload
menghilangkan state client. Receipt server tidak hilang. Jangan memulai batch baru sebelum
memastikan hasil yang tidak pasti. Export memakai filter yang telah diterapkan tanpa pagination.

Base path /api/v1. JSON; OpenAPI interaktif tersedia pada localhost:8000/docs.

Sprint 1A-02 menyediakan CRUD katalog di bawah. Tabel aktual didokumentasikan di DATABASE.md.
Endpoint `/ready` memeriksa revisi `0005_asset_imports`, tabel katalog, intent cleanup,
serta assets/asset_identifiers/asset_change_events/asset_import_batches. Task 1B-02 menyediakan endpoint
`/assets` dan allowlist CRUD proxy frontend; kontraknya ada di bagian terakhir.
Endpoint gambar tersedia pada Task 1A-03 di bawah; UI katalog tersedia sejak Task 1A-04.
Browser memakai localhost:3000/api/v1 melalui proxy allowlist.
Respons dari FastAPI memiliki Cache-Control: no-store dan X-Request-ID; proxy meneruskan keduanya dari upstream.
Error lokal proxy (400/404/405/413/503) memakai no-store dan nosniff; tidak mempunyai
X-Request-ID upstream bila request belum mencapai API.

OpenAPI `/openapi.json` mendeskripsikan `SessionCookie` (apiKey di cookie av_access),
header Origin/X-CSRF-Token wajib pada mutasi, batas query/version multipart,
response binary JPEG/PNG/WebP, dan X-Model-Version pada delete 204 tanpa body.
Cookie login tetap dikelola browser. Swagger bukan pengganti UI login: JavaScript browser
tidak dapat menyetel header Cookie/Origin secara bebas dan cookie HttpOnly tidak dapat dibaca.
Gunakan frontend same-origin atau HTTP client dengan cookie jar dan Origin sesuai konfigurasi.

| Metode dan path | Otorisasi | Hasil |
|---|---|---|
| GET /health | Publik | 200 {"status":"ok"}; tidak mengakses database |
| GET /ready | Publik | 200 {"status":"ready"} atau 503 jika DB/PostGIS/skema tidak siap |
| GET /auth/csrf | Publik | 200 {"csrf_token":"..."} + cookie av_csrf untuk login |
| POST /auth/login | CSRF + Origin | 200 user + cookie sesi; 401 kredensial salah/akun nonaktif |
| GET /auth/me | Akun aktif, sesi valid | 200 user; 401 bila anonim/kedaluwarsa/dicabut |
| GET /auth/session | Akun aktif, sesi valid | 200 {"csrf_token":"..."}; 403 bila cookie CSRF sesi hilang/tidak cocok |
| POST /auth/logout | Akun aktif + CSRF sesi + Origin | 204; mencabut sesi dan menghapus kedua cookie |
| GET /admin/status | ADMIN | 200 {"status":"ok","role":"ADMIN"}; 403 untuk role lain |

User response: {"id":"UUID","email":"you@example.com","name":"Administrator","role":"ADMIN"}.
Tidak pernah menyertakan hash password atau access token dalam JSON.

Login body:
```json
{"email":"you@example.com","password":"your-local-password"}
```

Email maksimal 254 karakter, password login 1–1024 karakter.
Bootstrap membuat password 12–128 karakter. Tidak ada endpoint pendaftaran atau pengelolaan pengguna.

## Browser request sequence

1. GET /auth/csrf dengan cookie credentials same-origin; simpan csrf_token di memori sementara.
2. POST /auth/login dengan JSON, header X-CSRF-Token, dan Origin asli browser.
3. Cookie HTTP-only av_access dan av_csrf dikirim otomatis oleh browser.
4. GET /auth/me untuk identitas. Dashboard melakukan pemeriksaan ini di server.
5. GET /auth/session untuk token sesi, lalu POST /auth/logout dengan X-CSRF-Token.
6. Setelah 401, UI meminta login ulang. Setelah 403, UI menampilkan penolakan izin/keamanan.

CSRF berlaku pada semua metode selain GET/HEAD/OPTIONS, termasuk login.
Origin harus cocok persis dengan ALLOWED_ORIGINS. CLI HTTP juga harus menyertakan Origin.
Cookie token dan header harus cocok, bertanda tangan valid; untuk mutasi sesi hash-nya harus cocok dengan sesi database.
Tidak ada dukungan bearer token dari browser atau query string.
Endpoint anonim /auth/csrf ditujukan untuk login; setelah login gunakan /auth/session. Cookie CSRF yang signature-nya masih valid dipertahankan tanpa memperpanjang masa berlaku agar pemanggilan ulang tidak merusak logout sesi aktif. Login berhasil tetap merotasi token.

## Errors

Format kesalahan: {"detail":"pesan"}.
422 menggunakan array detail berisi loc, type, msg, tanpa submitted input.
401 berarti autentikasi diperlukan/tidak valid; 403 berarti role, origin, atau CSRF ditolak.
503 berarti dependensi belum siap; proxy menggunakan status ini saat API tidak dapat dihubungi.
Kesalahan internal menghasilkan 500 tanpa stack trace atau informasi database.
Proxy menolak path di luar allowlist dengan 404 dan metode yang salah dengan 405; body POST di atas 16 KiB ditolak 413. Batas diterapkan saat streaming, termasuk tanpa Content-Length; pembacaan dihentikan ketika batas dilewati. Body stream yang rusak ditolak 400.

Cookie development menggunakan HTTP-only, SameSite=Lax, Path=/, tanpa Domain.
COOKIE_SECURE=true wajib saat production dengan HTTPS. Token default 15 menit dan tidak diperbarui otomatis.

## Device catalog — Task 1A-02

Semua route di bawah memakai base `/api/v1`. GET memerlukan akun aktif dan sesi valid
(ADMIN/OFFICER/VIEWER). POST/PATCH hanya ADMIN, dengan Origin dan CSRF sesi seperti Sprint 0.
Respons create 201; list/detail/update/archive 200. Tidak ada DELETE master katalog.

| Method | Route | Keterangan |
|---|---|---|
| GET / POST | /device-categories | List / create kategori |
| GET / PATCH | /device-categories/{id} | Detail / update termasuk is_active=false |
| GET / POST | /manufacturers | List / create manufacturer |
| GET / PATCH | /manufacturers/{id} | Detail / update termasuk is_active=false |
| GET / POST | /device-models | List / create model |
| GET / PATCH | /device-models/{id} | Detail / update / restore melalui is_active=true |
| POST | /device-models/{id}/archive | Archive tanpa menghapus UUID, foto metadata, atau referensi |

Route proxy browser pada port 3000 meneruskan endpoint tersebut, query string, cookie,
dan body PATCH. Allowlist hanya menerima UUID berbentuk standar untuk detail/archive;
ID malformed ditolak 404 oleh proxy, atau 422 jika langsung ke backend. Endpoint gambar
yang didokumentasikan di bawah juga di-allowlist. Batas body CRUD tetap 16 KiB.
Tidak ada halaman UI katalog.

### List dan filter

Semua list menerima `search` (maks. 200 karakter), `is_active` (opsional), `page`
(default 1; 1–1.000.000), dan `page_size` (default 25; 1–100). Parameter tak dikenal
ditolak 422. Tanpa is_active, list mencakup record aktif dan archived.

List model juga menerima `category_id`, `manufacturer_id` (UUID), dan `environment`
(`indoor`, `outdoor`, `both`). Semua filter digabung AND; UUID filter valid tetapi tidak
ditemukan menghasilkan list kosong. Search case-insensitive substring pada nama model,
alias individual, atau nama manufacturer. Search kategori mencakup name/code;
search manufacturer mencakup nama. Whitespace search dirapikan. `%` dan `_` adalah teks literal.

Urutan deterministik: nama lowercase/normalized ascending, lalu UUID ascending untuk tie-break.
Offset pagination bukan snapshot lintas request. Perubahan bersamaan dapat menggeser halaman;
total dan items dibaca oleh query terpisah pada isolasi DB default sehingga jumlah dapat berubah
di antaranya. Muat ulang daftar untuk hasil terkini. Pada data tetap, halaman tidak berulang
dan seluruh filter diterapkan pada count maupun items. Halaman melebihi akhir menghasilkan
items kosong dengan total asli; total_pages=0 hanya jika tidak ada hasil.
Pagination offset, bukan snapshot transaksi lintas request; daftar dapat bergeser bila ada
mutasi di antara permintaan halaman. Bentuk respons:

```json
{"items":[],"total":0,"page":1,"page_size":25,"total_pages":0}
```

Halaman di luar hasil tetap 200 dengan items kosong dan total sesuai filter.

### Input dan output

Category create: `code`, `name`, optional `description`, `is_active` (default true).
Code 1–50 karakter, trim/lowercase, pola `^[a-z0-9]+(?:-[a-z0-9]+)*$`; name 1–100 karakter.

Manufacturer create: `name` (1–150), optional `website` (HTTP/HTTPS valid, tanpa kredensial,
maks. 2048 setelah normalisasi URL), `is_active` (default true).

Model create:

```json
{
  "manufacturer_id":"UUID manufacturer aktif",
  "category_id":"UUID kategori aktif",
  "model_name":"AP680-L",
  "aliases":["AP 680-L"],
  "description":"Model katalog sintetis",
  "environment":"outdoor",
  "specs":{"bands":["2.4GHz","5GHz"],"poe":true},
  "is_active":true
}
```

model_name 1–200 karakter. Nama dan alias dirapikan menjadi satu spasi antarkata, tanpa
spasi tepi, mempertahankan kapitalisasi. Keunikan manufacturer/model memakai generated
lowercase key database. Model sama pada manufacturer berbeda boleh; archived tetap
mereservasi nama. Alias maksimal 20, masing-masing 1–200 karakter, unik setelah normalisasi
whitespace dan lowercase. Default aliases=[] dan specs={}. Description maksimal 4000 karakter.
Control karakter berbahaya dan unpaired Unicode surrogate ditolak, tanpa mengembalikan input.

Specs adalah object maksimal 32 key. Key 1–64 karakter `[A-Za-z0-9_.-]`. Value berupa
string (maks. 500 karakter), boolean, angka finite dalam +/-1e12, null, atau list maksimal
20 scalar tersebut. Nested object/list tidak didukung. Maksimum hasil encoding JSON UTF-8
specs 8192 bytes (termasuk separator default serializer). Spesifikasi bukan field bebas tanpa batas.

Output menyertakan field publik di atas plus `id`, `version`, `is_active`, timestamps,
`created_by`, dan `updated_by`. Field actor ditetapkan backend dari user sesi. Tidak ada
storage key, path filesystem, password, token, atau metadata gambar pada output master.

PATCH hanya mengubah field yang dikirim, **wajib menyertakan version dari GET terakhir**
dan setidaknya satu field perubahan. Field nullable yang boleh dikosongkan hanya description
dan website. ID, normalized key, timestamps, actor, dan field tak dikenal ditolak 422.
is_active harus boolean JSON; version harus integer JSON positif, bukan boolean/string.

```json
{"version":1,"description":"Diperbarui"}
```

Update sukses menaikkan version termasuk bila nilainya sama. Archive body:

```json
{"version":2}
```

Archive pertama menaikkan version. Archive ulang dengan version terkini idempotent tanpa
audit tambahan; version lama tetap ditolak 409. Kategori/manufacturer dinonaktifkan melalui
PATCH; tidak mengubah status model terkait. Model baru dan referensi parent yang diganti
harus menunjuk parent aktif. Edit metadata historis tidak memerlukan reaktivasi parent.
Restore model archived memeriksa kedua parent aktif.

### Errors dan audit

| Status | Kondisi |
|---|---|
| 401 | Sesi tidak valid/anonim/akun nonaktif (bila CSRF sudah valid untuk mutasi) |
| 403 | Role non-ADMIN pada mutasi, atau Origin/CSRF ditolak; termasuk anonim tanpa CSRF |
| 404 | UUID record valid tetapi record tidak ditemukan |
| 409 | Duplikasi code/nama, parent nonaktif, konflik versi, atau constraint race saat commit |
| 422 | Input/query tidak valid atau parent ID tidak ditemukan |

Error menggunakan `{"detail":"pesan aman"}`. Validasi request menggunakan
`{"detail":[{"loc":["body","field"],"type":"...","msg":"..."}]}` seperti Sprint 0,
tanpa `input`. Referensi tidak ditemukan menggunakan detail string (`Unknown category_id`
atau `Unknown manufacturer_id`). SQL dan nama constraint tidak dikirim ke client.
Error schema terdokumentasi di OpenAPI. CSRF tetap diperiksa sebelum handler katalog.

Semua mutasi menulis actor dan `catalog_create`/`catalog_update`/`catalog_archive` di audit_events
dalam transaksi yang sama. Detail audit berisi table, id, version; belum ada diff/snapshot
field lengkap. Kegagalan constraint/audit menggagalkan seluruh mutasi. Version request dan
version counter SQLAlchemy mencegah stale update serta race antar-session; client harus reload
setelah 409. Riwayat tidak dihapus oleh archive dan tidak ada API penghapusan audit.

## Reference images — Task 1A-03

Base `/api/v1/device-models/{model_id}/reference-images`:

| Method / suffix | Role | Hasil |
|---|---|---|
| POST collection | ADMIN + session CSRF/Origin | 201 `{image:{...},model_version:N}` |
| GET collection | Semua akun aktif | 200 `{items:[...],model_version:N}` |
| GET /{image_id}/content | Semua akun aktif | 200 bytes JPEG/PNG/WebP; no-store, nosniff |
| DELETE /{image_id}?version=N | ADMIN + session CSRF/Origin | 204 + header X-Model-Version |

Upload memakai multipart dengan tepat satu `file`, `version` model terkini (wajib), dan
`angle` opsional (nama 1–100 karakter setelah normalisasi whitespace). Field lain/duplikat
ditolak. Nama file dari client diabaikan. Tidak ada field storage_key atau path host pada input/output.
Contoh curl setelah memperoleh cookie dan CSRF sesi melalui alur auth existing:

```bash
curl -b session-cookies.txt -H 'Origin: http://localhost:3000' \
  -H 'X-CSRF-Token: SESSION_CSRF' \
  -F 'version=1' -F 'angle=front' -F 'file=@synthetic.png;type=image/png' \
  http://localhost:3000/api/v1/device-models/MODEL_UUID/reference-images
```

Hanya JPEG/PNG/WebP yang signature dan Content-Type-nya cocok, dapat di-verify/decode penuh,
serta berisi satu frame. File kosong, rusak, SVG/GIF, animasi, decompression bomb, atau gambar
melebihi batas ditolak sebelum file permanen/metadata dibuat. Extension tidak dipercaya.
EXIF orientation diterapkan, lalu pixel ditulis ulang tanpa EXIF/GPS, ICC, text/XMP, dan
payload tambahan. Hash SHA-256 dan byte_size dihitung dari hasil sanitasi yang benar-benar disimpan.

Batas configurable di README: default file 8 MiB (juga hasil sanitasi), sisi 8192,
16 juta pixel, dan 20 foto/model. IMAGE_MAX_PER_MODEL minimum 5. Request upload total
dibatasi file limit + 64 KiB overhead melalui stream backend; proxy memiliki ceiling
8 MiB + 64 KiB. Batas CRUD tetap 16 KiB. Content-Length tidak diperlukan agar batas efektif.
Decode diserialisasi per proses untuk membatasi penggunaan memori; tidak ada inference GPU.

Metadata image: id, device_model_id, sha256, mime_type, byte_size, angle, is_primary,
uploaded_by, created_at, dan `content_url` relatif menuju route content di atas.
Tidak mengembalikan filename asli, storage_key, atau direktori filesystem.
List berurutan created_at lalu UUID; bounded oleh jumlah maksimum foto/model.
Foto pertama primary otomatis; saat primary dihapus, foto tersisa paling awal menjadi primary.
Belum ada endpoint pemilihan primary manual atau modifikasi metadata foto.

Upload/delete menaikkan version model dan mencatat audit reference_image_upload/delete
dalam transaksi metadata yang sama. Lock model menserialisasi count/primary/version.
Client wajib memakai model_version baru dari upload/list/detail, atau X-Model-Version dari delete.
Version lama mendapat 409; delete yang diulang setelah sukses mendapat 404 bila version sudah terkini.
Model archived tetap dapat dibaca dan fotonya dihapus secara eksplisit oleh ADMIN;
upload baru ke model archived ditolak 409. Archive sendiri tidak menghapus foto.

Error tambahan mengikuti envelope detail existing:

- 400: multipart malformed atau terlalu banyak part; pesan parser disanitasi.
- 413: file/request/hasil sanitasi melebihi batas byte.
- 415: bukan multipart, format tidak diizinkan, atau mismatch MIME/signature.
- 422: field multipart tidak valid, decode gagal, animasi, dimensi/pixel berlebih.
- 409: stale version, jumlah foto maksimum, model archived, atau constraint race.
- 404: model/image tidak ditemukan, image milik model lain, atau bytes hilang.
- 503: storage tidak tersedia atau integrity hash/ukuran bytes yang disimpan tidak cocok.

GET content selalu memeriksa sesi dan pasangan model/image; tidak ada mount static publik,
URL host path, atau URL cloud. Metadata yang sudah dihapus tidak dapat dipakai untuk mengambil bytes.
Menurunkan batas upload tidak menyembunyikan file existing yang valid (hard ceiling read 8 MiB).

File dan DB bukan satu transaksi filesystem bersama. Implementasi memakai intent durable
`storage_cleanup_jobs`: upload membuat intent sebelum put eksklusif, lalu menghapus intent saat
metadata/audit commit. Gagal upload mencoba kompensasi langsung; bila cleanup gagal atau proses
berhenti, intent tetap tersedia. Delete commit metadata removal + intent terlebih dahulu,
lalu unlink. Kegagalan unlink tetap menghasilkan 204 karena resource sudah hilang dari API;
bytes privat dipertahankan sampai retry, tanpa kehilangan catatan cleanup.

Retry operasional: `docker compose exec api python -m app.storage_cleanup`.
Maksimal 100 intent berusia >10 menit per run; gunakan ulang untuk backlog. Retry memakai lock,
idempotent untuk file yang sudah hilang, dan tidak menghapus key yang masih direferensikan image.
Tidak ada pemindaian atau penghapusan file lain, worker otomatis, atau layanan eksternal.

## Pemakaian oleh frontend katalog (Task 1A-04)

Halaman `/catalog/models`, `/catalog/models/new`, `/catalog/models/[id]`, dan
`/catalog/settings` memakai kontrak existing melalui proxy `/api/v1`. Tidak ada endpoint baru.
List memakai page_size 15 dan filter search/category_id/manufacturer_id/is_active;
pengelolaan kategori/produsen memakai page_size 10. Pilihan referensi form membaca semua
halaman, menampilkan referensi inactive existing saat edit, dan membatasi pilihan baru ke aktif.
Mutation mengambil token CSRF sesi; PATCH/archive mengirim version baseline draft/record.
Upload sequential memakai model_version dari list kemudian response upload terakhir;
DELETE memakai query version. Tidak ada retry otomatis untuk mutasi yang gagal.
Frontend menampilkan pesan Indonesia untuk 401/403/404/409/413/415/422/5xx;
backend tetap melakukan validasi authoritative, termasuk MIME/decode dan batas workspace.

## Physical asset CRUD — Task 1B-02

Semua rute di bawah memakai prefix `/api/v1`, cookie dan CSRF existing. GET untuk
ADMIN/OFFICER/VIEWER aktif; seluruh mutasi hanya ADMIN. Respons privat/no-store.

| Method | Route | Kontrak |
|---|---|---|
| GET | /assets | Page[AssetOutput], search/model_id/status/page/page_size |
| POST | /assets | AssetCreate → 201 AssetOutput dan event CREATE |
| GET | /assets/{asset_id} | AssetOutput atau 404 |
| PATCH | /assets/{asset_id} | version + field berubah → AssetOutput |
| POST | /assets/{asset_id}/archive | {version} → AssetOutput |
| GET | /assets/{asset_id}/identifiers | Array klaim aktif; urut created_at, UUID |
| POST | /assets/{asset_id}/identifiers | asset_version + klaim → 201 IdentifierMutation |
| PATCH | /assets/{asset_id}/identifiers/{identifier_id} | version + asset_version + field berubah |
| DELETE | /assets/{asset_id}/identifiers/{identifier_id} | Query version dan asset_version → 200 IdentifierMutation |

AssetCreate wajib asset_code dan device_model_id. Code di-trim/uppercase, ASCII huruf/angka
di awal lalu huruf/angka/_/-, 1–50 karakter. Lifecycle default IN_STOCK, condition UNKNOWN.
Field lain: notes (nullable, maks. 4000), purchase_date (nullable YYYY-MM-DD), installed_at
(nullable ISO datetime dengan timezone). Tidak ada field serial_number tunggal, lokasi,
atau identifiers nested. Buat klaim secara eksplisit melalui endpoint identifier.
AssetOutput berisi id, asset_code, device_model_id, lifecycle_status, condition, notes,
purchase_date, installed_at, created_at, updated_at, version. Model dan unit tetap terpisah.

PATCH aset menerima device_model_id/lifecycle_status/condition/notes/purchase_date/installed_at;
minimal satu field selain version, hanya notes/tanggal boleh null. asset_code/id dan field
lain ditolak 422. Version JSON wajib integer (bukan bool/string), rentang 1–2147483647.
Version stale/limit mendapat 409. Asset PATCH yang sukses menaikkan version; archive berulang
dengan version terkini adalah no-op. PATCH status ARCHIVED juga diaudit sebagai ARCHIVE;
ADMIN dapat mengubahnya kembali lewat PATCH tanpa mengganti identitas.
Model tidak dikenal 422; model inactive untuk create/reassignment 409. Referensi historis
yang tidak berubah tetap boleh diedit. Tidak ada DELETE unit.

List: default page=1/page_size=25, maksimum page=1000000/page_size=100; status memakai enum
lifecycle, model_id UUID. Default mencakup semua status termasuk ARCHIVED. Urutan asset_code
lalu UUID; total_pages=0 jika kosong, page di luar rentang items=[]. Offset pagination bukan
snapshot lintas request. Search substring case-insensitive pada code atau nilai identifier
aktif (termasuk SN/hostname/management ID); input MAC lengkap compact/colon/hyphen/dotted
juga dicocokkan terhadap nilai kanonis. Karakter wildcard diperlakukan literal. Query asing
ditolak 422. Beberapa klaim cocok tetap menghasilkan satu unit.

Klaim wajib identifier_type, raw_value (1–255 printable, bukti asli dipertahankan), source;
verification_status default UNVERIFIED dan notes opsional. Enum mengikuti DATABASE.md.
MAC dinormalisasi; SN kosong/UNKNOWN/N/A/NA/- ditolak (SN hilang berarti tanpa baris).
PATCH boleh mengganti tipe/raw/source/verification_status/notes, wajib minimal satu perubahan;
normalisasi memvalidasi pasangan tipe+raw setelah digabung dengan nilai existing. normalized_value,
id, asset_id, created_at dan deleted_at tidak dapat ditulis client.

IdentifierMutation = {identifier: IdentifierOutput, asset_version: int}. IdentifierOutput:
id, asset_id, identifier_type, raw_value, normalized_value, source, verification_status,
notes, created_at, deleted_at, version, collision_asset_ids. Version identifier naik saat
PATCH/DELETE dan version aset induk naik pada add/PATCH/DELETE. Gunakan version terbaru
dari setiap respons; jangan retry konflik secara otomatis. DELETE mengembalikan klaim
soft-deleted beserta version terbaru; retry dengan version terkini no-op. PATCH klaim
terhapus mendapat 409. Klaim milik unit lain mendapat 404.

Duplikat aktif satu aset+tipe+nilai mendapat 409; lintas aset diperbolehkan dan ditampilkan
melalui collision_asset_ids, tanpa overwrite/merge. Collision hanya tipe/nilai sama dan
klaim aktif, termasuk unit archived. Audit CREATE/UPDATE/ARCHIVE/IDENTIFIER_ADD/UPDATE/REMOVE
memuat aktor/waktu dan before/after snapshot dalam transaksi domain yang sama. Field snapshot
`asset` berisi AssetOutput; event identifier juga berisi `identifier` (tanpa collision_asset_ids).
Audit belum diekspos lewat API. Error mengikuti envelope detail existing; tidak membuka SQL.
Proxy web hanya mengizinkan rute/metode di atas, batas body CRUD 16 KiB.
CSV tersedia pada Task 1B-03 di bawah. Foto unit dan UI aset belum tersedia.

## Asset CSV — Task 1B-03

Ketiga route khusus ADMIN aktif; OFFICER/VIEWER 403, anonim/nonaktif/revoked 401.
POST membutuhkan Origin dan X-CSRF-Token sesi existing. Tidak ada public import/link export.

| Method | Route | Request / response |
|---|---|---|
| POST | /api/v1/assets/imports/preview | JSON {csv_text} → 200 CsvPreview; tanpa DB write |
| POST | /api/v1/assets/imports/commit | JSON {csv_text, idempotency_key, allow_identifier_collisions?: false} → 200 CsvCommitResult atau 409 |
| GET | /api/v1/assets/export.csv | search/model_id/status opsional → CSV UTF-8 BOM attachment assets.csv |

Input file dibaca menjadi teks UTF-8 oleh client; endpoint menerima JSON, bukan multipart.
Batas stream JSON 1 MiB pada backend/proxy sebelum JSON parse, juga tanpa Content-Length.
Batas csv_text 256 KiB UTF-8, 500 data row, header wajib unik/known. CSV comma delimiter,
quoted commas/newlines didukung, CRLF/LF dan satu BOM UTF-8 didukung. Blank data lines diabaikan;
header harus record pertama. Nomor row memakai urutan record logis (header=1), bukan baris fisik
di dalam quoted multiline. Empty/header-only/malformed CSV atau header asing → 422.
Unknown JSON fields/UUID key invalid/flag non-bool/CSV melebihi batas → 422; body >1 MiB → 413;
media selain application/json → 415. Semua batas tetap berlaku pada API langsung.

Header wajib: asset_code,manufacturer,model. Opsional: serial_number,mac_address,hostname,
condition,status,notes,location_hint. Nama header di-trim, case-sensitive. Field opsional kosong
diabaikan (status IN_STOCK, condition UNKNOWN). Nama produsen/model dikanonisasi whitespace
dan case-insensitive; kode di-trim/uppercase. Model wajib dikenal/aktif dan tidak dibuat otomatis.
SN/MAC/hostname mengikuti validasi API 1B-02; source IMPORT/verifikasi UNVERIFIED.
Notes maks. 4000, location_hint maks. 1000 dan hanya staging di receipt, bukan field aset.
CSV tidak menerima UUID aset, version, source, tanggal atau field lain sebagai jalan update.

CsvPreview = {total_rows, valid_rows, invalid_rows, has_collisions, rows}. Setiap row:
{row, asset_code, valid, errors: string[], collisions: [...], location_hint, asset_id:null,
version:null}. Collision = {identifier_type, normalized_value, asset_ids: UUID[], csv_rows:int[]}.
Duplikat code internal menandai semua row terkait invalid; code existing/archived invalid.
Collision tipe/nilai sama lintas unit/CSV adalah warning yang memerlukan flag pengakuan eksplisit
pada commit; klaim terhapus tidak dihitung. Model/format/column-count errors ditampilkan per row.

Commit memvalidasi ulang CSV dan kondisi DB, tidak mempercayai report preview client.
Batch atomik: semua row berhasil atau tidak ada row yang ditulis. CsvCommitResult:
{import_id: UUID, status: COMMITTED|REJECTED, created_count, failed_count, rows, errors}.
COMMITTED row berisi asset_id dan version baru (1 + jumlah klaim), serta staged hint.
REJECTED memakai 409, created_count=0, failed_count=total; errors row dan/atau errors batch
menjelaskan kegagalan. Konflik SQL/audit di tengah batch juga rollback receipt/domain/audit,
asset_id/version hasil kerja sementara dihapus dari report. Field valid pada row adalah
hasil validasi row, bukan klaim row sudah committed; periksa status batch.

Idempotency key UUID dibuat client satu kali per payload. Receipt sukses persisten dalam DB,
transactional dengan aset/audit, unique global key dan terikat aktor serta SHA-256 CSV persis
(termasuk whitespace/BOM) + flag collision. Retry identik mengembalikan report sukses yang sama,
tanpa create/event tambahan, dan tidak terpengaruh perubahan katalog sesudah sukses. Key reuse
dengan aktor/payload berbeda → 409 envelope {detail:string}; OpenAPI mendokumentasikan kedua
bentuk 409. Payload gagal tidak menyimpan receipt/reservasi key. Jangan membuat key baru hanya
karena timeout; retry key lama. Baseline version dari receipt adalah saat import, bukan latest.

Export memakai filter pencarian 1B-02 tanpa pagination, urut code/UUID, default seluruh status.
Maksimum 5000 unit atau 16 MiB output; lebih → 413 dan gunakan filter. Query asing termasuk
page/page_size ditolak. Kolom: seluruh header import di atas, lalu id,version,purchase_date,
installed_at,identifiers_json. Scalar SN/MAC_LAN/hostname memakai nilai kanonis, banyak nilai
dipisah newline dalam quoted cell. identifiers_json memuat semua klaim aktif beserta tipe,
raw/normalized, source/verifikasi/notes/id/version/waktu; termasuk MAC_WLAN/BSSID/MANAGEMENT_ID.
Klaim soft-deleted tidak diekspor. location_hint kosong karena bukan lokasi master.
CSV writer mengutip delimiter/newline/quote; sel formula (=,+,-,@ sesudah whitespace) atau
berawalan tab/CR/LF diberi apostrof, termasuk notes/nama/SN. Tidak mengubah nilai database.
Export adalah laporan, bukan roundtrip import/backup: ada kolom tambahan dan sanitasi nilai.
Seluruh response private/no-store/nosniff, attachment tanpa path/credential/storage key.
UI upload/preview/confirm baru menjadi Task 1B-04 dan belum tersedia.

## Asset location — Task 2-02

GET `/api/v1/assets/{id}/location` tersedia bagi semua role authenticated: asset_id,
version, current_location_id, location_verified_at dan location (LocationOutput, termasuk
lokasi yang diarsipkan). Aset belum ditempatkan menghasilkan 200 dengan tiga nilai lokasi
null; UUID aset unknown 404. GET list/detail aset juga menyertakan dua kolom nullable baru.
Pencarian tujuan memakai GET /locations dengan search/is_active/parent_id existing.

POST `/api/v1/assets/{id}/initial-placement` khusus ADMIN, JSON maksimal 16 KiB:
`{"version":1,"location_id":"UUID","reason":"Verifikasi penempatan awal"}`.
Origin/CSRF sesi wajib. Sukses 201 AssetOutput, version +1, timestamp UTC server dan
event INITIAL_PLACEMENT dicatat dalam transaksi yang sama. Ini keputusan awal langsung
oleh ADMIN; tidak membuat request movement atau self-approval policy untuk Task 2-03.
Reason wajib nonblank, canonical whitespace, maksimal 2000 karakter; timestamp/aktor,
current_location_id dan field ekstra dari client ditolak. Unknown location 422, lokasi/
aset archived atau stale/already placed/version limit 409. Retry setelah respons terputus
menghasilkan 409 jika sudah berhasil; baca ulang lookup, tidak membuat event kedua.

Hanya is_active tujuan lokal diperiksa, sesuai semantik Task 2-01; ancestor archived tidak
mengarsipkan descendants. Arsip lokasi setelah penempatan mempertahankan FK dan bukti.
location_verified_at berarti waktu keputusan verifikasi awal ADMIN, bukan sensor GPS atau
jaminan posisi fisik terus-menerus. installed_at, lifecycle_status dan identifier tidak berubah.
PATCH/create aset umum, CSV dan seed tidak menerima/memetakan lokasi. Event tersimpan dalam
asset_events; endpoint timeline/movement/observasi dan UI baru belum disediakan pada 2-02.

## Movement state machine — Task 2-03

| Method | Route | Role |
|---|---|---|
| GET | /api/v1/assets/{id}/movements | Semua role authenticated, history aset |
| POST | /api/v1/assets/{id}/movements | OFFICER/ADMIN, 201 |
| GET | /api/v1/movements | ADMIN, inbox/list |
| GET | /api/v1/movements/{id} | Semua role authenticated, detail |
| POST | /api/v1/movements/{id}/approve | ADMIN |
| POST | /api/v1/movements/{id}/reject | ADMIN |
| POST | /api/v1/movements/{id}/cancel | ADMIN atau OFFICER pembuat request |

Request JSON: `{"asset_version":2,"to_location_id":"UUID","reason":"Pindah ke Villa 10"}`.
Origin dan expected_asset_version disalin server dari aset terkunci. asset_version adalah
versi aset yang ditinjau client; stale 409. Reason wajib canonical nonblank, maksimal 2000
karakter; unknown field termasuk from/status/requester/timestamp ditolak. Aset harus sudah
memiliki initial placement eksplisit 2-02; unplaced/archived, tujuan sama atau archived
menghasilkan 409; unknown tujuan 422. Tujuan active bersifat lokal, mengikuti 2-01.
Lokasi asal archived boleh ditinggalkan. Request menyimpan snapshot lokasi saat dibuat,
bukan mutasi lokasi/version aset. Lebih dari satu PENDING per aset diperbolehkan.

Decision JSON approve/reject/cancel: `{"version":1,"reason":"Keputusan setelah review"}`.
Version adalah movement version; seluruh keputusan memerlukan reason. Hanya PENDING dapat
menjadi APPROVED/REJECTED/CANCELLED. Terminal final; replay/versi stale 409, tanpa event kedua.
Approve memeriksa ulang asset version, from_location_id, status aset dan tujuan aktif dalam
transaksi yang sama. Sukses 200 MovementOutput, movement version +1, asset version +1,
FK lokasi/verified_at berpindah dan MOVEMENT_APPROVED tercatat. reviewed_at = approved_at =
effective_at adalah waktu UTC server saat keputusan; tidak menerima backdate atau jadwal.
Request lain menjadi stale dan tetap PENDING sampai ditolak/dibatalkan serta dibuat ulang.

Reject/cancel 200 hanya mengubah status/version/reviewer/review_reason/time movement dan
mencatat event, tanpa mengubah aset, timestamp verifikasi atau asset version. Dapat menutup
request stale/tujuan archived. Cancel OFFICER hanya request sendiri; ADMIN boleh cancel
siapa pun. Approve/reject/inbox selalu ADMIN. Self-approval ADMIN **diizinkan untuk pilot**,
dengan requester/reviewer tetap, self_approval boolean serta policy ALLOWED_PILOT pada event.

Response MovementOutput berisi id, asset_id, from/to_location_id, status, reason,
requested_by/at, expected_asset_version, request_snapshot_json (from/to LocationOutput),
reviewed_by/at, review_reason, approved_at, effective_at, version. Snapshot request immutable;
arsip/rename tidak menulis ulang history. Bukti keputusan juga menyimpan snapshot tujuan
saat approval. Event tersimpan di asset_events; timeline API baru pada Task 2-04.

List/history menerima status opsional, page 1–1 juta dan page_size 1–100 (default 20).
Tanpa status membaca semua; inbox juga menerima asset_id opsional. Order requested_at DESC
lalu UUID DESC; offset bukan snapshot lintas request. Field/query ekstra ditolak. Unknown
asset/detail movement 404; inbox filter asset unknown menghasilkan daftar kosong. Semua
mutasi memakai sesi/Origin/CSRF existing, JSON stream maksimal 16 KiB di API/proxy;
non-JSON 415, oversized 413. Tidak ada PATCH/delete movement. Frontend hanya proxy allowlist,
belum ada UI. Tidak ada initial placement massal, auto-approval atau perubahan CSV.

## Timeline dan observasi — Task 2-04

| Method | Route /api/v1 | Role |
|---|---|---|
| GET | /assets/{id}/timeline | Semua role authenticated |
| GET | /assets/{id}/location-status | Semua role authenticated |
| GET | /assets/{id}/location-observations | Semua role authenticated |
| POST | /location-observations | OFFICER/ADMIN; 201 |
| GET | /location-observations | ADMIN inbox |
| GET | /location-observations/{id} | ADMIN detail |
| POST | /location-observations/{id}/review | ADMIN; 200 |

Create JSON: `{"asset_id":"UUID","asset_version":3,"observed_location_id":"UUID",
"evidence_note":"Unit ditemukan di Villa 1","observed_at":"2026-10-19T03:00:00Z"}`.
asset_id/asset_version harus hadir berpasangan atau sama-sama null/absent untuk perangkat
unlinked. Note canonical nonblank maksimal 2000 karakter. observed_at opsional (default UTC
server), wajib berzona waktu dan tidak di masa depan; offset dinormalisasi UTC. recorded_at,
aktor, comparison, snapshot, reviewer dan version ditentukan server. Unknown field ditolak.
Unknown aset 404, unknown lokasi 422, stale asset version atau lokasi observed archived 409.
Aset archived boleh mendapat bukti lapangan; tidak mengaktifkan atau memindahkannya.

Output berisi id, asset_id nullable, observed_location_id, observed_by, observed_at, recorded_at,
evidence_note, official_location_id_at_recording, asset_version_at_recording, comparison_status
(UNLINKED/UNPLACED/MATCH/LOCATION_CONFLICT), snapshot_json, review_status, reviewed_by/at,
review_reason dan version. Snapshot menyimpan observed/official lokasi dan konteks aset saat
pencatatan. comparison_status adalah perbandingan saat direkam, bukan proyeksi status terkini.

Review JSON: `{"version":1,"review_status":"ACKNOWLEDGED","reason":"Sudah diperiksa"}`
atau DISMISSED. Hanya PENDING → salah satu terminal sekali; version menjadi 2. Stale/replay
409. ACKNOWLEDGED berarti telah ditinjau, tetap menjadi bukti aktif; bukan resolusi mismatch.
DISMISSED mengecualikan bukti dari proyeksi terkini tetapi tidak menghapus sejarah. Koreksi
melalui observasi baru; tidak ada edit/delete/relink evidence. Semua write memakai sesi,
Origin/CSRF existing, body JSON maksimal 16 KiB; 415 non-JSON dan 413 oversized. Role 401/403.
Tidak ada mutasi assets/current_location/version dari create maupun review.

History/inbox menerima review_status/comparison_status, page 1–1 juta, page_size 1–100
(default 20). Inbox menambah asset_id atau unlinked_only=true (mutually exclusive). Order
observed_at DESC, recorded_at DESC, id DESC. Unknown query ditolak. Unlinked tidak dimasukkan
ke timeline aset mana pun; audit create/review tetap tersimpan pada audit_events existing.

Location-status mengembalikan asset_id/version, current_location_id, location_verified_at,
status, location_conflict dan latest_observation nullable. Latest adalah observasi terkait
yang tidak DISMISSED, diurutkan observed_at/recorded_at/id DESC. UNPLACED jika lokasi resmi
null; NO_OBSERVATION jika belum ada bukti aktif; STALE_OBSERVATION jika observed_at sebelum
location_verified_at. Selain itu MATCH atau LOCATION_CONFLICT menurut lokasi resmi saat
GET. location_conflict=true hanya untuk LOCATION_CONFLICT. Bukti lama tidak auto-revert
movement terbaru; observasi bukan verifikasi fisik atau identitas otomatis.

Timeline menerima source=METADATA/LOCATION dan event_type opsional serta pagination bounded
sama. Item: id, source, asset_id, actor_id, event_type, occurred_at, recorded_at,
correlation_id nullable, payload_json. METADATA membaca asset_change_events (occurred_at =
recorded_at legacy, correlation null, payload before_json/after_json); LOCATION membaca
asset_events termasuk initial placement, movement, LOCATION_OBSERVED dan
LOCATION_OBSERVATION_REVIEWED. Sort occurred_at DESC, recorded_at DESC, source DESC, id DESC;
identitas item adalah (source,id). Payload/precision timestamp existing tidak ditulis ulang.
Backdated observation ditempatkan menurut waktu observasi, review menurut waktu keputusan.
Offset pagination/count bukan snapshot lintas request saat event baru masuk. Semua GET
read-only/no-store; unknown aset/detail observation 404. Tidak ada endpoint append/edit/delete
timeline bebas. Frontend hanya proxy allowlist, tanpa UI Task 2-05.

## Konsumen frontend — Task 2-05

Halaman `/locations` memakai GET /locations/tree dan mutasi ADMIN POST/PATCH locations.
Tree adjacency dirender sebagai daftar hierarkis berindentasi dengan path/tingkat; pencarian
mempertahankan konteks ancestor. Node archived tetap ditampilkan, parent dirinya/descendant
keluar dari pilihan edit. Backend tetap menguji cycle/version dan status lokasi lokal.
UI tidak mengirim atau menghapus kolom GPS existing saat edit nama/parent/status.

Detail aset memakai location-status, tree, movements, location-observations dan timeline.
Initial placement, request movement, cancel/review dan observasi/review memakai payload domain
2-02–2-04 existing. Tidak menambah endpoint, field master, schema atau izin backend. Version
dibekukan saat formulir dibuka; body JSON maksimal 16 KiB, sesi/CSRF dari auth/session, no-store.
Setiap hasil simpan yang tidak pasti/error menghentikan submit ulang, mempertahankan draft
sampai pembatalan/reload eksplisit. UI tidak memakai optimistic relocation.

`/movements` diperiksa server untuk ADMIN dan mengulang otorisasi pada API. OFFICER hanya
mendapat cancel request sendiri berdasarkan user UUID sesi; backend tetap memeriksa ownership.
Approval UI dinonaktifkan bila asset version/origin stale, aset archived atau tujuan inactive;
API memvalidasi ulang pada transaksi. Riwayat preview menampilkan lima event terbaru, dengan
link ke detail aset untuk seluruh timeline. Inbox berfilter status/page_size10; history aset
movements/observations page_size5, timeline page_size10 dengan filter source. Semua dapat
membaca timeline; detail snapshot tetap read-only. Error sesi menyediakan tautan login.
