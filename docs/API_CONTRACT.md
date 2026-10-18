# API Contract

Base path /api/v1. JSON; OpenAPI interaktif tersedia pada localhost:8000/docs.

Sprint 1A-02 menyediakan CRUD katalog di bawah. Tabel aktual didokumentasikan di DATABASE.md.
Endpoint `/ready` memeriksa revisi `0003_image_cleanup`, tabel katalog, dan intent cleanup.
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
