# Business Rules

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
