# Observasi dan review perangkat — Task 3-05

Buka `/recognition` setelah login. OFFICER/ADMIN mengunggah satu foto perangkat dan foto label
opsional, meninjau kandidat model/similarity, mengisi koreksi label, memilih lokasi master dan
mencatat observasi. VIEWER membaca riwayat/detail yang sudah tersimpan. Foto yang belum dipakai
hanya terlihat oleh pemilik/ADMIN; daftar pemulihan unggahan menampilkan milik akun sendiri.

Default mempertahankan NO_GO3-01: encoder dan Paddle tidak diaktifkan pada API default.
Tanpa index hasil UNKNOWN_MODEL; index tanpa adapter/kalibrasi tetap UNCERTAIN. Tidak ada
pemilihan encoder/threshold produksi, pencarian web/cloud atau pembuatan katalog/unit otomatis.
Koreksi manual tetap tersedia dan dapat menghasilkan kandidat identifier, bukan approval.
Status tidak dikenali/perangkat baru menyimpan observasi unlinked dan menonaktifkan forced match.

## Penyimpanan dan transaksi

Migration0011 menambah tiga tabel kosong tanpa UPDATE/backfill pada master existing:
- recognition_jobs: satu pembacaan MODEL/OCR selesai, metadata source SHA, original image key,
  actor/time dan hasil DTO3-02/3-03 immutable. Tidak ada queue/worker service baru.
- survey_observations: references ke job, lokasi/waktu, note, request UUID/digest, raw OCR,
  parsed identifiers, corrected_text/manual_candidates, visual provenance, fusion3-04 dan
  context fingerprint immutable. Snapshot kandidat unit memuat version/claims; tidak menyalin
  seluruh registry ke setiap observasi. Inbox berisi ringkasan, detail memuat evidence lengkap.
- recognition_reviews: satu keputusan immutable per observation, aktor/waktu/reason, selected
  model/unit nullable dan evidence review terpisah. Prediksi awal tidak diganti. Asset_id output
  diturunkan dari selected_asset_id review, bukan relink/UPDATE prediksi awal.

Seluruh UPDATE/DELETE tiga tabel ditolak trigger SQLite/PostgreSQL. FK mempertahankan konteks.
Populated downgrade ditolak sebelum DROP. SQL owner tetap bertanggung jawab menggunakan policy
aplikasi; trigger bukan otorisasi pengguna atau pelindung terhadap database superuser.

Observasi/review dan AuditEvent commit atomik. Create menggunakan request_id UUID + digest
payload Pydantic untuk retry actor/payload yang sama (mengembalikan ID lama), key berbeda aktor/
payload mendapat409. Concurrent loser dapat menerima409; tidak ada overwrite/duplicate otomatis.
Review satu terminal lewat unique observation_id; racing decisions hanya satu berhasil.
Tidak ada auto-retry, auto-merge, silent version replacement atau perubahan asset/identifier/
current_location/verified_at/lifecycle/master/version oleh recognition.

PostgreSQL menggunakan transaksi SERIALIZABLE khusus survey; hierarchy→asset locks berurutan
menjaga eligibility lokasi dan parent identifier. Complete snapshot max500 unit/128 relevant
claims per unit/64000 total, latest non-dismissed location observation dan latest approved
placement/movement dibaca bounded/correlated; tidak memakai pending movement. Fingerprint juga
mengikat catalog references dan embedding head/version. Perubahan konteks sejak observasi
membuat MATCH409 (termasuk perubahan unrelated registry, sengaja konservatif). Serialization/
deadlock menjadi409 tanpa retry. SQLite bukan pembuktian race; pengujian race memakai PG.

## Kebijakan review v1

Hanya ADMIN aktif dapat review. ADMIN boleh mereview observasinya sendiri untuk pilot;
created_by/reviewer_id/waktu tetap tercatat terpisah dan policy label unik tetap wajib. Pilihan UNKNOWN, CONFLICT, MORE_PHOTOS tidak memilih unit/model.
MATCH membutuhkan semua berikut:
- label_checked eksplisit sesudah manusia memeriksa sumber/label; note wajib;
- checked_manual_indices yang menunjuk kandidat pada koreksi manual yang telah tersimpan;
- tipe SN/MAC_LAN/MAC_WLAN yang valid, SN dengan manufacturer UUID tepat;
- klaim master VERIFIED yang cocok pada unit terpilih, unit aktif/tidak archived dan version sama;
- complete snapshot/fingerprint masih sama; fusion ulang PROBABLE_ASSET tepat satu unit tanpa
  konflik identifier/model/lokasi/histori atau collision, termasuk klaim unit archived lain.

MATCH merekam VERIFIED_ASSET **hanya pada keputusan manusia ini**, bukan output fusion3-04 atau
status master. Model+lokasi, raw OCR ber-score tinggi, generic MAC/BSSID, unchecked manual,
UNVERIFIED/DISPUTED master, stale/ambiguous/conflict tidak cukup. Perbaikan master/placement/
movement harus lewat workflow ADMIN existing; tidak disisipkan dalam recognition.
Butuh koreksi bukti setelah immutable save/MORE_PHOTOS: catat observasi baru; jangan edit sejarah.

## Upload, akses dan batas

Upload multipart hanya fieldfile tunggal, authenticated OFFICER/ADMIN dengan CSRF/Origin sesi.
Original bytes bounded max8MiB (workspace dapat lebih kecil), JPEG/PNG/WebP magic+MIME,
4096side/16Mpixel/singleframe. Nama/path dari browser diabaikan. EXIF original tetap privat
untuk provenance; SHA original dicatat. Endpoint content memverifikasi SHA dan mengembalikan
preview JPEG max1600side tanpa EXIF/GPS; tidak menyediakan original sebagai static URL.
Penurunan limit upload tidak menyembunyikan bukti lama yang valid. Dua preview/worker dan satu
inference/worker serentak; busy429. JSON64KiB, koreksi16Kchars/128lines/512chars per line.

Original disimpan lewat StorageProvider Sprint1A; durable StorageCleanupJob dibuat sebelum put,
exclusive UUID key, cleanup melindungi reference image **dan recognition job** pada ambiguous
commit. Capture+audit+intent removal atomik; orphan-file recovery tanpa directory scan. Bukti
capture tanpa observasi tetap retained/private dan dapat dipulihkan di UI. Maks20 unattached
MODEL dan20 OCR per akun; limit tidak memblokir pencatatan observasi untuk memakai foto itu.
Data observasi/foto historis tidak dihapus otomatis; operator perlu memperhitungkan disk lokal.
Rate10 upaya recognition writes/menit/akun, termasuk malformed upload, audit attempt durable
serialized per-user; 429 Retry-After. Default API satu worker; tidak ada Redis/distributed queue.
Logs tidak menulis body/label/filename/path/SQL parameter. Semua response no-store/nosniff.

## API `/api/v1/recognition`

| Method | Route | Akses / input |
|---|---|---|
| POST | /model-candidates | OFFICER/ADMIN, multipartfile; simpan job MODEL + SearchResult |
| POST | /ocr | OFFICER/ADMIN, multipartfile; simpan job OCR + raw evidence/fallback |
| GET | /jobs | semua akun, hanya pending milik akun sendiri |
| GET | /jobs/{id} dan /jobs/{id}/content | pemilik/ADMIN, atau semua akun bila attached ke observasi |
| POST | /observations | OFFICER/ADMIN; request_id,device_job_id,label_job_id?,location?,correction?,notes,force_unknown? |
| GET | /observations | semua akun; pagination page/page_size, ringkasan |
| GET | /observations/{id} | semua akun; prediksi/evidence awal + review terpisah |
| POST | /observations/{id}/review | ADMIN; version1,decision,notes dan checked evidence untuk MATCH |
| GET | /metrics | ADMIN; hitungan operasional, accuracy=null, NO_GO_REAL_DATASET_REQUIRED |

Browser tidak dapat mengirim visual score/result, master snapshot, human_checked atau engine
setting sebagai input observasi. Manufacture/asset/version review diverifikasi ulang server.
HTTP401/403/404/409/413/415/422/429/503; unknown bukan error. Next proxy allowlist method/path,
streamed body caps, forwarding cookie/CSRF/Retry-After. Form menjaga draft, synchronous submit
guard dan membekukan pengiriman bila gagal/tidak pasti; periksa riwayat/pending lalu reload.

## Opt-in CPU environment

Tidak perlu untuk alur manual. Default API tetap kecil, tidak memasang torch/paddle/download.
`compose.recognition-api.yaml` hanya override eksplisit terhadap API lokal, tidak dijalankan
oleh test/deploy default. Build memakai existing pinned environment, tanpa unduhan weights baru:

```bash
# Visual experimental: bangun environment index3-02 dahulu sesuai RECOGNITION_INDEX.md.
RECOGNITION_CPU_BASE=assetvision-recognition-index:3-02 \
  docker compose -f compose.yaml -f compose.recognition-api.yaml build api
# OCR experimental: environment OCR3-03 sesuai OCR.md.
RECOGNITION_CPU_BASE=assetvision-ocr:3-03 \
  docker compose -f compose.yaml -f compose.recognition-api.yaml build api
```

Variabel override (tidak mengedit .env existing otomatis):
RECOGNITION_ENCODER_NAME optional mobilenet_v3_small/shufflenet_v2_x0_5 (blank=None);
RECOGNITION_WEIGHTS_ROOT absolut default/opt/weights/hub/checkpoints;
OCR_MODELS_ROOT optional absolut /opt/ocr-models (blank=None);
RECOGNITION_CPU_BASE build-only nama image lokal, default index3-02. Pilih base yang mempunyai
packages/local pinned weights terkait; tidak mengaktifkan dua engine pada satu base tanpa
menyiapkan environment gabungan secara eksplisit. Tidak mengklaim gabungan sudah diuji.

Optional API CPU2/mem2GiB/read-only/tmpfs256MiB/capdrop/pid256, storage original tetap RW privat.
Visual child deadline10s untuk spec dan10s encode; OCR15s. Parent tidak mengimpor torch/Paddle.
Model missing/mismatch/timeout tetap UNCERTAIN/manual fallback. Child version/weight checks dari
3-02/3-03 dipertahankan. Runtime tidak mengunduh. Ini enablement eksperimental, **bukan GO encoder**.
Untuk menjalankan override, set env terkait saat `docker compose -f compose.yaml -f
compose.recognition-api.yaml up -d --no-deps api` (contoh OCR_MODELS_ROOT=/opt/ocr-models
pada baseOCR). Blank tidak mengaktifkan inference. Default development deployment task ini
memakai compose.yaml saja. Jangan rebuild/kalibrasi index development tanpa perintah operator
terpisah.

## Validasi

`bash infra/check.sh --postgres`; `bash infra/smoke-recognition.sh` dijalankan sesudah semua
writer db-test berakhir. Unit/API/SSR/jsdom memakai data sintetis, termasuk race PG dan rollback
jika audit gagal. Image CPU terpisah menjalankan6encoder/5OCR tests (termasuk HTTP OCR nyata),
networknone/read-only. Tidak ada klaim accuracy perangkat nyata atau evaluasi E2E Task3-06.
Hasil aktual/iterasi/preservasi dan daftar berkas: sprints/SPRINT_3_05_REPORT.md.
