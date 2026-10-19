# Evaluasi end-to-end recognition — Task 3-06

Evaluasi ini menguji alur aplikasi dan kebijakan identitas dari Task3-01–3-05. Data sintetis
bukan dataset akurasi perangkat. Encoder produksi, threshold dan klaim top-3≥90% tetap
NO_GO sampai tersedia dataset nyata independen sesuai RECOGNITION_EVALUATION.md.

## Lapisan bukti dan batas

| Lapisan | Yang dijalankan | Yang dibuktikan |
|---|---|---|
| Integrasi API | TestClient + migrations + SQLite/PostgreSQL + storage privat sementara | index/search top3, upload, OCR/koreksi, snapshot8unit, fusion, review, audit dan master tetap |
| Transport nyata | Next SSR/proxy + FastAPI + PostgreSQL/PostGIS db-test melalui HTTP | auth/RBAC, upload default tanpa adapter, unknown, konflik lokasi, false-positive review dan checked match |
| Profil encoder | Dua encoder CPU pinned, enam foto WP810 dan seluruh 15 foto lokal read-only, proses terpisah | latency/peakRSS per encoder; bukan top-k/unknown accuracy |

Fixture API mempunyai empat model warna sintetis dan delapan unit identik model AP. Index
benar-benar dibangun dan pencarian benar-benar menghitung similarity. Index tidak diberi
kalibrasi. Untuk menguji cabang visual accepted, test menyuntikkan hasil acceptance **sesudah
search** dengan reason SYNTHETIC_ACCEPTANCE_BRANCH_ONLY. Ini batas dependency test yang
sengaja eksplisit, bukan laporan kalibrasi nyata palsu. Tidak ada policy ADMIN_REVIEWED_REAL_
EVALUATION baru disimpan. Skenario uncalibrated menjalankan search apa adanya dan menolak
penggunaan ranking visual untuk menebak unit. Encoder/OCR fixture diberi nama synthetic-only.

Sembilan skenario integrasi:

1. SN rusak/tidak terbaca, model accepted dan Lounge unik → PROBABLE_ASSET, asset_id null;
   MATCH tanpa identifier diperiksa ditolak, keputusan MORE_PHOTOS tersimpan.
2. Empat AP identik di lokasi sama → AMBIGUOUS, tidak ada verifikasi berdasarkan lokasi saja.
3. Delapan AP identik tanpa lokasi/identifier → delapan kandidat AMBIGUOUS.
4. Tidak dikenali dipilih eksplisit → UNKNOWN/unlinked walau ada ranking visual.
5. SN milik AP-003 diamati di Villa10, master Villa1 → prediksi unchecked tetap memisahkan
   kandidat; saat label diperiksa, MATCH ditolak409; review CONFLICT tidak memindahkan unit.
6. Manual SN AP-001 tetapi reviewer memilih AP-002 →409, lalu MORE_PHOTOS unlinked.
7. Manual SN unik VERIFIED, scope produsen, versi dan lokasi sesuai → hanya review ADMIN
   yang menghasilkan VERIFIED_ASSET; prediksi awal tetap utuh.
8. OCR synthetic score0.99 salah menunjuk AP-003, koreksi AP-001 terpisah; memilih AP-003
   ditolak, pemeriksaan manual AP-001 dapat disetujui. Raw OCR tidak dihapus.
9. Index belum terkalibrasi → UNCERTAIN model, UNKNOWN unit, manual review tetap wajib.

Semua skenario memeriksa actor/time/audit dan membandingkan seluruh response master delapan
unit sebelum/sesudah. Transport HTTP memakai delapan unit yang dibuat/placed lewat API,
empat observasi dan empat keputusan terminal; dua percobaan MATCH salah ditolak409.
API production tidak diedit atau diberi test flag; fixture/injection hanya berada di tests/.

## Menjalankan secara serial

Dari root repo Ubuntu WSL2. Jangan jalankan dua writer db-test bersamaan.

```bash
bash infra/check.sh --postgres
# Stack HTTP terisolasi; path report harus BARU dan parent sudah ada:
bash infra/evaluate-recognition.sh /tmp/recognition-e2e-new.json
# Profil CPU lokal yang sudah memiliki pinned weights, tidak download saat run:
bash infra/benchmark-recognition.sh data/samples/grandstream-wp810 \
  data/recognition-eval/wp810-new-run data/recognition-eval/wp810-profile-v1/manifest.json
```

Runner HTTP membangun image, memakai db-test tmpfs dan foto tmpfs, mengaplikasikan migration
pada database test saja, lalu menghentikan web-smoke/api-smoke/db-test lewat trap. Tidak
menjalankan migrate/seed/rebuild terhadap database development. Tiga layanan smoke diberi
batas resource eksplisit; development API/web/db tidak di-restart. Port3002 hanya loopback.
Report existing ditolak tanpa overwrite. Tidak commit foto/weights/report privat per-image.
Profil foto hanya menggunakan data pengguna yang telah tersedia; manifest/provenance serta
izin foto tetap diperiksa manusia sesuai protokol3-01. Dataset baru tidak diambil otomatis.

## Arti metrik

Report HTTP hanya berisi agregat: jumlah synthetic assets/scenario, latency count/p50/p95/max,
resource counters dan NO_GO. Tidak ada password/cookie/image/identifier/path privat. Latency
mencakup transport HTTP + proxy + validasi + API/DB untuk request yang diukur, tanpa GET sesi/
CSRF/setup. Satu sesi serial dingin, PNG32x24, tanpa warmup: ukuran sample kecil, termasuk
respons review409; bukan pengukuran kapasitas/concurrency, foto smartphone8MiB atau SLA.

Resource collector memerlukan Linux cgroup-v2 memory.peak/memory.max/cpu.stat. Peak memory
adalah lifetime cgroup termasuk startup, setup, page cache dan buffer, bukan RSS proses saja.
CPU delta diambil sebelum/sesudah workload termasuk login/setup/health traffic. Bukan RAM host,
bukan konsumsi gabungan lingkungan CPU opsional, tidak termasuk runner test. Bandingkan peak
per layanan dengan limit yang tercatat; jangan menyimpulkan kapasitas produksi dari fixture ini.
Jika subprocess tes mengembalikan status nonzero, report ditandai FAILED. Timeout atau error
collector menghentikan proses dan dapat meninggalkan file report kosong/tidak lengkap; file
tersebut bukan hasil sukses dan rerun harus memakai path report baru.

Profil encoder3-01 mengukur decode/preprocess/encoder/search/end-to-end offline; profile-only
reference_count0 dan search tanpa referensi, metrics/threshold null. PeakRSS proses dan peak
cgroupHTTP berbeda metrik. Jangan menjumlahkan atau membandingkannya tanpa memperhatikan scope.
Tidak ada benchmark OCR perangkat nyata atau environment gabungan torch+paddle dalam task ini.

## Dataset lokal yang diperiksa

Pengguna menyediakan data/samples: AP680-L: 3, Grandstream WP810: 6, Lenovo IdeaPad Slim 3: 5,
unknown: 1 (total 15 foto). Validasi image/hash lolos, tetapi belum ada pembagian capture independen
atau reference/calibration/test/unknown_calibration/unknown_test. Dengan tiga knownmodel dan
satu unknown, batas minimum protokol3-01 belum terpenuhi. Semua15 dapat diprofilkan dengan
manifest profile-only lokal, tanpa mengubah source foto atau membuat threshold. Token
unclassified-profile-only untuk foto folderunknown hanya label profil, bukan model katalog.

## Gate rilis

Manual fallback dan policy review dapat diuji sekarang. Untuk memilih encoder/threshold dan
menilai false acceptance visual, kumpulkan >=4 model, referensi/calibration/test independen,
unknown calibration/test, beberapa unit/model, label rusak/buram dan variasi kamera/cahaya.
Delapan AP sintetis membuktikan aturan ambigu; delapan AP nyata tidak otomatis menjadi delapan
model atau split independen. Jangan mengubah threshold dari sample test atau mematikan leakage
guard. Accuracy/top1/top3/unknown precision/recall tetap null bila dataset tidak layak.
Tidak menyatakan Sprint3 memenuhi seluruh acceptance accuracy sebelum bukti tersebut tersedia.
