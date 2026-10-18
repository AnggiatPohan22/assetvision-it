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
