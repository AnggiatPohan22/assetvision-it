# Sprint 2 — UAT lokasi, movement dan audit

Tanggal eksekusi: 19 Oktober 2026 (Asia/Makassar). Scope Task 2-05.
UAT browser dijalankan melalui in-app browser pada **http://localhost:3002**, bukan development
localhost:3000. Stack Next.js/API/PostgreSQL nyata, database tmpfs assetvision_test dengan
host db-test dan user test_runner. Guard test memeriksa target sebelum membuat akun sintetis.

## Menjalankan ulang

1. Dari Ubuntu WSL2, pastikan suite PG/smoke lain berhenti. Jalankan
   `bash infra/smoke-location-ui.sh --uat`. Hanya db-test yang dibuat ulang; DB/storage
   development tidak disentuh. Tanpa --uat runner menjalankan SSR smoke dan otomatis berhenti.
2. Runner mencetak direktori /tmp acak. session.json lokal berisi UUID AP-003/lokasi dan
   akun acak untuk ADMIN/OFFICER/VIEWER beserta password test. Permission file 0600,
   direktori 0700. Gunakan akun tersebut pada localhost:3002/login; jangan memakai akun
   development atau menyimpan credential test di Git/laporan/screenshot.
3. Ikuti skenario di bawah melalui UI. Fixture awal memiliki UAT Site, Villa 1, Villa 10,
   Lounge dan Lobby; AP-003 unplaced dengan satu event metadata. Jangan mengandalkan UUID
   dari run sebelumnya karena setiap runner membuat ulang fixture terisolasi.
4. Akhiri logout, pulihkan viewport bila diubah dan hentikan stack test:

```bash
docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test stop web-smoke api-smoke db-test
```

## Hasil browser aktual

| Skenario | Hasil diamati |
|---|---|
| ADMIN buka tree dan buat lantai di bawah Villa 1 | Lantai tampil pada tingkat 3 dengan path ancestor |
| ADMIN edit/arsip lantai | Save berhasil; node tetap retained, tidak dihapus |
| AP-003 awal | Unplaced/version1, SN tidak tersedia tanpa SN palsu |
| ADMIN initial placement Villa 1 dengan alasan | Official Villa 1/version2, verifikasi dan event Penempatan awal tampil |
| OFFICER request Villa 1 → Villa 10 | PENDING, official tetap Villa 1/version2; tombol cancel milik sendiri tersedia |
| ADMIN inbox | Snapshot request, AP-003, current Villa 1/version2, alasan/requester/waktu serta tiga event histori terlihat |
| ADMIN approve dengan alasan | Inbox pending kosong, official Villa 10/version3, event persetujuan tampil |
| OFFICER observed Villa 1 setelah approve | Badge LOCATION_CONFLICT, official tetap Villa 10/version3, bukti dan actor/time ada di timeline |
| ADMIN ACKNOWLEDGED | Bukti Sudah ditinjau, event review ada; conflict tetap, official/version tidak berubah |
| VIEWER detail | Official, conflict, movement, evidence dan timeline terbaca; kontrol create/review/placement tidak tersedia |
| VIEWER direct /movements | Halaman Akses terbatas; nav inbox tidak ditampilkan |
| VIEWER /locations | Tree terbaca, tombol Tambah/edit tidak ada |
| Filter timeline Metadata aset | Hanya event metadata Aset dibuat tampil; tidak melakukan mutasi |
| ADMIN arsip Villa 1 setelah movement/observasi | Official tetap Villa 10; evidence snapshot Villa 1 dan event review tetap terlihat |
| Logout lalu request baru /locations | Kembali ke /login; juga diuji HTTP SSR/API401 |
| Mobile 390×844 | Form/select/textarea/tombol tersusun vertikal, tidak ada overflow horizontal (document width375 <= viewport390) |

Perpindahan, observasi dan review dilakukan dengan interaksi form browser, bukan injeksi state
atau fetch console. In-app browser sempat dibuka sebelum stack siap (connection refused),
lalu dibuka ulang setelah service healthy. Pemilihan select memakai locator combobox setelah
locator label exact tidak cocok dengan teks label yang membungkus options; tidak ada perubahan
izin atau data development. Saat logout, navigasi terlalu cepat menghasilkan error sesi pada
client; setelah masuk kembali ke halaman login, request halaman baru terverifikasi redirect.

Pembacaan SQL test setelah UAT mengonfirmasi AP-003 official Villa 10/version3, movement APPROVED,
requester dan reviewer berbeda, observation ACKNOWLEDGED/version2, lima event lokasi dengan
correlation unik dan satu event metadata. Snapshot observed Villa 1 tetap tersimpan meskipun
asal archived. Ini verifikasi persistensi, bukan pengganti interaksi browser.

Screenshot sintetis desktop dan form mobile disimpan pada folder visualizations lokal Codex:
`sprint-2-05-desktop.png`, `sprint-2-05-mobile.png`. Lokasi absolut ada pada laporan 2-05.
Tidak ada data/foto asli atau screenshot credential pada artefak tersebut. Viewport dipulihkan
dan stack UAT dihentikan sebelum regresi PG berikutnya. File credential sementara dari run
ini dihapus sesudah UAT.

## Keadaan negatif dan batas pengujian

React/jsdom menjalankan uji 409 mempertahankan draft/version, unknown network result tidak
retry, dua submit pending hanya satu request, role/ownership cancel, stale approve diblokir
namun reject tersedia, initial placement ADMIN saja, invalid timezone, expiry/login recovery,
preview unavailable menonaktifkan submit, filter/pagination dan empty state. Hasil suite lengkap
tercantum pada laporan. Constraint/rollback/race PG dan API seluruh role tetap diuji suite
backend predecessor; tidak mengklaim semua kombinasi race dibuat manual di browser.

UAT agent adalah pemeriksaan penerimaan teknis pada satu browser/viewport desktop dan 390×844.
Bukan persetujuan bisnis operator, uji perangkat fisik lintas browser, benchmark 5000 node,
atau audit aksesibilitas penuh. Floorplan/pin opsional ditunda; input koordinat GPS dan
observasi unlinked memakai API existing. Tidak melanjutkan recognition/Sprint 3.
