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
