# Business Rules

## Hierarki lokasi — Task 2-01

Location berbeda dari penempatan aset. SITE/BUILDING/FLOOR/ROOM/AREA/SPOT dapat menjadi
root/child; tidak memaksakan urutan kind universal karena struktur outdoor/indoor bervariasi.
Parent wajib existing, tidak boleh self/descendant. Kode lowercase ASCII dengan separator
hyphen, 1–50 karakter, unik per parent dan unik antar root. Kode arsip tetap direservasi.
Nama dinormalisasi whitespace, maksimum 200 karakter. UUID tetap; rename/reparent melalui
PATCH version dengan audit actor/waktu/before/after dalam transaksi yang sama.

ADMIN saja dapat mutasi; OFFICER/VIEWER read-only. PATCH wajib version integer positif;
stale 409 tanpa overwrite. Setiap PATCH valid menaikkan version, termasuk nilai sama.
Arsip `is_active=false` tidak cascade, tidak memutus parent/child atau menyembunyikan sejarah.
Parent archived tidak menerima child baru, pemindahan masuk, atau restore child; edit metadata
child historis dengan relasi tetap diperbolehkan. Status active bersifat lokal, bukan agregat
seluruh ancestor. Memindah/restore ke parent aktif atau root diperbolehkan.

Koordinat berpasangan dalam rentang latitude ±90/longitude ±180, akurasi nonnegatif maksimal
10 juta meter, waktu GPS berzona jika tersedia. Akurasi/waktu memerlukan koordinat.
PATCH memvalidasi hasil gabungan; menghapus koordinat memerlukan pengosongan akurasi/waktu
juga bila ada. Tidak ada geocoding/inference lokasi, floorplan, placement atau movement.
Audit memakai AuditEvent existing dengan details before/after berisi JSON string; tidak ada
API edit/delete audit. Trigger lokasi tidak menjamin setiap writer SQL menulis audit dan
bukan proteksi terhadap database owner/superuser. Downgrade menolak tabel lokasi berisi data.

## UI registry — Task 1B-04

Daftar/detail dan riwayat metadata dapat dibaca ADMIN/OFFICER/VIEWER. Halaman tambah/impor
dibatasi ADMIN di server; tombol mutasi disembunyikan untuk role baca. Backend tetap memeriksa
role, CSRF dan version setiap request. Asset ID tidak pernah dikirim dalam PATCH. Draft memakai
version saat edit dimulai, konflik mempertahankan isian dan tidak memicu retry otomatis.
SN tidak tersedia/rusak ditampilkan sebagai badge informasi, bukan identifier placeholder.
Unit dibuat terlebih dahulu, identifier ditambah terpisah agar kegagalan klaim tidak dianggap
sebagai kegagalan pembuatan unit. Sumber/verifikasi bukti dipilih eksplisit dan collision
menautkan unit lain tanpa merge. Penghapusan klaim tetap soft-delete dengan konfirmasi.

Impor hanya dapat dikonfirmasi setelah preview valid dan benturan identifier diakui.
File baru membatalkan preview/acknowledgement. Setelah commit tidak pasti, file/flag dikunci
dan retry mempertahankan request/key yang sama selama halaman terbuka. Sesudah batch ditolak,
preview wajib diulang. Riwayat UI membaca snapshot existing, tidak menyediakan edit audit.
Foto unit opsional belum ditambahkan. Seed delapan AP disediakan pada 1B-05.

## Seed sintetis — Task 1B-05

Seed hanya development/test, aktor ADMIN aktif, konfirmasi CLI eksplisit. Batch berisi
AP-001…AP-008 pada Ruijie AP680-L, tidak menyatakan unit produksi. SN contoh AP-001 123456789,
AP-002 2158763; AP-004/AP-005 tidak punya klaim SN. Notes unit/klaim dan snapshot CREATE
menandai SYNTHETIC; seluruh klaim bersumber IMPORT dan belum diverifikasi.
Kategori/produsen/model existing tidak diubah, termasuk metadata, versi dan status arsip.
Kode existing tidak boleh diadopsi walau nilai/model sama. Model dengan unit non-seed,
collision identifier, UUID terpakai, referensi tidak aktif atau batch parsial ditolak atomik.
Tidak mengisi kekurangan/menimpa edit pada rerun batch lengkap. Audit aktor/waktu/before/after
memakai transaksi yang sama; gagal audit membatalkan katalog, unit dan klaim sekaligus.
Contoh delapan unit bukan batas jumlah unit sebuah model pada domain normal.

Aturan domain berikut tetap berlaku untuk sprint berikutnya. Sprint 0 tidak membuat tabel aset atau alur operasional.

1. DeviceModel (definisi model perangkat) dan AssetUnit (unit fisik) merupakan entitas terpisah.
2. Asset ID bersifat immutable.
3. Serial number dapat hilang, tidak terbaca, atau rusak.
4. Lokasi saja tidak pernah membuktikan identitas fisik.
5. Observasi survei tidak langsung menimpa master aset yang telah disetujui.
6. Perpindahan aset harus memiliki riwayat yang dapat diaudit.
7. Perangkat yang belum dikenal harus didukung.
8. Hasil AI merupakan bukti pendukung, bukan keputusan final.
9. Perubahan penting harus dapat diaudit.
10. Perubahan bersamaan tidak boleh saling menimpa secara diam-diam.

## Access rules Sprint 0

| Akses | ADMIN | OFFICER | VIEWER |
|---|---|---|---|
| Login akun aktif | Ya | Ya | Ya |
| Current user / dashboard / logout | Ya | Ya | Ya |
| GET /admin/status | Ya | 403 | 403 |
| Pengelolaan pengguna / aset | Belum tersedia | Belum tersedia | Belum tersedia |

Pengguna anonim menerima 401 untuk API terlindungi dan diarahkan ke halaman login saat membuka dashboard.
Akun nonaktif ditolak saat login dan saat memakai token lama. Hak akses dibaca dari database.
Tidak ada registrasi publik dan tidak ada kredensial bawaan.
Bootstrap hanya untuk admin pertama, idempotent, tidak mengubah akun yang sudah ada,
dan menggunakan transaksi serta advisory lock PostgreSQL agar bootstrap bersamaan tidak membuat beberapa admin.

Jejak audit autentikasi disimpan dalam transaksi yang sama dengan perubahan sesi.
Tidak ada API untuk mengubah atau menghapus jejak audit pada Sprint 0.

## Access dan audit katalog Sprint 1A

ADMIN dapat mengelola kategori/produsen/model dan upload/delete foto. OFFICER/VIEWER
hanya membaca, termasuk content foto privat. Backend memeriksa role database pada setiap request;
kontrol UI tidak menggantikan pemeriksaan API. Referensi model historis tetap ada setelah archive.

Create/update/archive memakai audit catalog_create/catalog_update/catalog_archive dengan actor,
table, record UUID, version, timestamp. Perubahan status melalui PATCH dicatat sebagai update.
Archive berulang pada version terbaru tidak mengubah data dan tidak membuat audit tambahan.
Upload/delete foto memakai reference_image_upload/reference_image_delete dengan model_id,
image_id, dan version model baru. Kegagalan audit menggagalkan perubahan domain pada transaksi itu.
Penolakan validasi/RBAC/konflik tidak menghasilkan audit sukses. Failed login memiliki event sendiri;
tidak semua percobaan API yang ditolak disimpan sebagai event domain. Belum ada diff field penuh,
UI audit, retensi otomatis, atau jaminan tamper-proof terhadap administrator database.

## Schema unit fisik — Task 1B-01

AssetUnit adalah unit fisik terpisah, menunjuk device_models.id valid. Asset code dinormalisasi
uppercase ASCII, 1–50 karakter: diawali huruf/angka, berikutnya huruf/angka/underscore/hyphen.
UUID dan asset_code tidak dapat diubah melalui UPDATE, termasuk SQL langsung. DELETE aset
ditolak; archive mempertahankan baris dan reservasi kode selamanya. Model yang direferensikan
tidak dapat dihapus; model nonaktif tetap valid sebagai referensi historis.

Unit tanpa serial tidak mempunyai baris SERIAL_NUMBER. Tidak memakai SN palsu UNKNOWN/N/A/NA/-.
Klaim wajib memiliki tipe, raw value, normalized value, sumber, dan status verifikasi.
MAC_LAN/MAC_WLAN/BSSID dibedakan; MAC disimpan AA:BB:CC:DD:EE:FF, hostname lowercase,
serial/management ID trim dengan case dipertahankan. Raw evidence tetap disimpan.
Duplikat aktif dalam (asset, tipe, normalized value) ditolak. Lintas aset/tipe diperbolehkan
dan dapat dicari lewat index lookup untuk penanganan collision di task API/CSV berikutnya.
Belum ada tipe yang terbukti unik global, termasuk serial yang belum didisambiguasi per produsen;
tidak menambahkan constraint unik global atau merge otomatis. Banyak MAC per tipe tetap boleh.

Identifier memakai deleted_at untuk soft-delete dan version ORM. DELETE fisik ditolak;
UUID dan asset_id klaim tidak bisa dipindahkan. Event audit aset memiliki actor wajib,
waktu server, tipe aksi dan snapshot before/after JSONB. UPDATE/DELETE event ditolak.
Skema saja belum mewajibkan setiap SQL writer menghasilkan event. API Task 1B-02 menulis
snapshot dan perubahan domain dalam satu transaksi serta memeriksa version client.
Seperti katalog, counter ORM menolak stale updates, tetapi SQL bulk harus menangani version sendiri.
Trigger tidak menjadi perlindungan tamper-proof terhadap pemilik database/superuser.
Belum ada lokasi aktif, movement, OCR/AI, foto unit atau UI aset.

## API unit fisik — Task 1B-02

ADMIN mengelola aset dan identifier. OFFICER/VIEWER hanya membaca; anonim/nonaktif/sesi
dicabut ditolak. Mutasi wajib Origin dan CSRF sesi existing. Tidak ada hard-delete unit.
Create tanpa SN diperbolehkan; endpoint identifier terpisah mencatat bukti setelah unit dibuat.
Code/UUID ditolak sebagai field PATCH, termasuk bila nilainya sama. Model baru/relasi baru
harus aktif; referensi model yang sudah archived tetap sah untuk sejarah dan edit metadata.

Status/kondisi tetap vocabulary 1B-01 tanpa workflow transisi. ADMIN dapat mengubah status,
termasuk memulihkan ARCHIVED melalui PATCH; code tetap dipertahankan. Masuk ARCHIVED melalui
PATCH atau endpoint archive menghasilkan event ARCHIVE. Archive berulang dengan version
terkini tidak mengubah data/version atau menambah event. PATCH lain menaikkan version walau
nilainya sama, sesuai pola katalog. Tanggal installed_at wajib timezone jika diberikan.

POST identifier memakai asset_version; PATCH/DELETE memakai version identifier dan
asset_version. Setiap mutasi klaim menaikkan kedua version (add dimulai pada version 1),
sehingga form metadata lama juga mendapat 409. DELETE adalah soft-delete; retry memakai
kedua version terkini bersifat no-op, retry version lama 409. Klaim terhapus tidak dapat
diubah/dipulihkan; buat klaim pengganti dengan UUID baru. Snapshot event identifier memuat
aset induk dan klaim yang berubah. Tidak ada audit sukses untuk request gagal.

Duplikat aktif dalam unit+tipe+nilai kanonis menghasilkan 409. Collision nilai sama lintas
unit/tipe tidak menggabungkan atau menimpa bukti. Respons identifier menghitung
collision_asset_ids untuk klaim aktif dengan tipe/nilai kanonis sama di unit lain;
lintas tipe tidak dianggap collision. Ini informasi saat baca, bukan reservasi global
atau jaminan snapshot terhadap transaksi lain. Klaim terhapus tidak ikut lookup/pencarian.
Tidak ada endpoint audit, foto unit atau seed baru pada Task 1B-02. CSV tersedia sejak 1B-03.

## CSV unit fisik — Task 1B-03

Preview/commit/export khusus ADMIN, memakai sesi/CSRF existing untuk POST. Impor hanya
menambah unit baru: kode existing (termasuk archived) ditolak, tidak ada update/upsert,
rename, merge atau auto-create katalog. Manufacturer/model dicocokkan dengan nama kanonis
case-insensitive, harus model aktif. Semua row diperiksa ulang saat commit; preview bukan
reservasi kode/model. Batch maksimum 500 row, UTF-8 CSV maksimum 256 KiB.

Preview menghasilkan error per row, duplicate code internal, konflik kode DB, unknown/inactive
model, dan collision identifier aktif internal CSV/DB. SN kosong berarti tanpa klaim.
serial_number → SERIAL_NUMBER, mac_address → MAC_LAN, hostname → HOSTNAME; source IMPORT
dan verification UNVERIFIED. Collision lintas unit adalah evidence yang boleh disimpan
hanya bila allow_identifier_collisions=true secara eksplisit pada commit. Deteksi adalah
pembacaan pada transaksi saat validasi, bukan uniqueness global/reservasi identifier.

Commit memakai csv_text yang divalidasi ulang dan idempotency_key UUID dari client.
Semua row, klaim, audit dan receipt berhasil atau seluruhnya rollback. Satu row invalid
atau collision yang belum diakui menolak seluruh batch (created_count=0, failed_count=total).
Successful receipt mengikat UUID ke aktor dan digest CSV persis + flag collision. Retry
aktor/payload sama mengembalikan hasil tersimpan tanpa mutasi/audit tambahan, meskipun
data katalog/aset sudah berubah sesudah sukses; role aktif tetap dicek pada setiap request.
Key berbeda aktor/payload mendapat 409. Kegagalan tidak mereservasi key permanen.
Retry setelah timeout harus memakai key/payload persis yang sama. Receipt berisi version
saat import; baca detail terbaru sebelum mengedit unit.

location_hint hanya tersimpan pada laporan/receipt import sebagai staging non-authoritative.
Tidak disalin ke notes atau current_location. Export mengosongkan kolom location_hint.
Export satu row per unit, seluruh status termasuk ARCHIVED secara default, memakai filter
search/model_id/status. Semua klaim aktif disertakan dalam identifiers_json agar banyak
MAC/tipe lain tidak hilang; kolom scalar memuat nilai kanonis dipisahkan newline.
Nilai berawalan formula (=,+,-,@ setelah whitespace) atau tab/CR/LF diberi apostrof.
Export bukan backup/format roundtrip import; mengandung kolom pelaporan tambahan dan
sanitasi formula. Tidak ada penghapusan data/audit atau location workflow melalui CSV.

## Initial placement — Task 2-02

- Lokasi resmi awal dipilih eksplisit oleh ADMIN untuk aset unplaced dan tidak archived;
  hanya boleh sekali. Penempatan selanjutnya memerlukan movement workflow Task 2-03.
- current_location_id nullable adalah lokasi resmi terakhir, bukan bukti tunggal identitas
  atau posisi fisik saat ini. location_hint tidak pernah dipetakan otomatis.
- Keputusan ADMIN mencatat waktu verifikasi server, reason dan event INITIAL_PLACEMENT
  atomik dengan increment version. Tidak mengubah lifecycle, tanggal instalasi atau klaim.
- Lokasi tujuan harus aktif lokal; lokasi/ancestor mengikuti semantik arsip Task 2-01.
  Snapshot event mempertahankan konteks saat penempatan walau lokasi diubah/diarsipkan.
- PATCH umum dan impor tidak boleh mengubah lokasi. Replay penempatan menolak 409; event
  koreksi/movement belum diimplementasikan. Existing aset tetap unplaced setelah migrasi.

## Movement workflow — Task 2-03

- OFFICER/ADMIN dapat mengajukan request untuk aset placed dan tidak archived. Origin dan
  expected version diambil server, destination wajib berbeda/aktif lokal, reason wajib.
  Aset unplaced memakai initial placement 2-02 terlebih dahulu. Tidak menafsirkan hint CSV.
- Request hanya PENDING dan tidak mengganti lokasi/version. Beberapa PENDING boleh ada;
  approve pertama yang valid membuat snapshot request lain stale, bukan auto-reject.
- ADMIN approve membandingkan version/origin dan eligibility ulang. Satu transaksi mengubah
  lokasi resmi, waktu verifikasi, asset/movement version, reviewer dan event approval.
  Metadata atau identifier edit setelah request juga membuatnya stale 409.
- PENDING hanya bisa APPROVED/REJECTED/CANCELLED sekali; terminal tidak dapat diedit/dihapus.
  Reject/cancel tidak mengubah aset. Request stale harus ditutup dan dibuat ulang setelah review.
- ADMIN approve/reject; ADMIN atau OFFICER pembuat dapat cancel. VIEWER baca saja, bukan inbox.
  Self-approval ADMIN diizinkan untuk pilot, dicatat flag dan policy ALLOWED_PILOT pada event.
- Reason keputusan wajib; requested/reviewed/approved/effective time dari server. Tidak ada
  backdating/scheduling. Lokasi asal boleh archived; tujuan harus aktif saat request/approval.
  Arsip setelah keputusan mempertahankan referensi, snapshot dan seluruh event.

## Bukti lokasi dan review — Task 2-04

- Observasi adalah bukti lapangan, bukan perubahan master atau bukti tunggal identitas.
  OFFICER/ADMIN mencatat lokasi, note dan waktu; asset/version opsional untuk unknown device.
  Tidak ada auto-link/auto-create berdasarkan lokasi, maupun auto-approve movement.
- Create/review tidak mengubah official location, verified time, lifecycle atau asset version.
  Aset archived/unplaced tetap dapat menerima bukti. Lokasi observed harus aktif lokal.
- Aktor/recorded time/snapshot resmi/comparison ditentukan server; waktu observasi timezone
  aware, tidak future, boleh backdated. Snapshot dan evidence tidak dapat diedit/dihapus.
- ADMIN meninjau sekali menjadi ACKNOWLEDGED atau DISMISSED dengan reason/version wajib.
  ACK tidak menghapus conflict. DISMISS mengeluarkan bukti dari proyeksi, sejarah tetap ada.
  Koreksi evidence melalui record baru, bukan overwrite/relink. Unknown tetap unlinked.
- Latest non-dismissed observation dipilih berdasarkan waktu fisik observed_at lalu
  recorded_at/id. Jika lebih tua daripada verification resmi, status STALE_OBSERVATION;
  selain itu mismatch adalah LOCATION_CONFLICT, tanpa memindahkan lokasi resmi.
- Semua role dapat membaca history/timeline/status aset. Inbox/detail/review observasi hanya
  ADMIN. Linked event dan keputusan append-only; unlinked diaudit tanpa asset palsu.
