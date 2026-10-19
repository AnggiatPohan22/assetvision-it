# Recognition evaluation — Task 3-01

Alat offline berada di `tools/recognition_eval`, terpisah dari aplikasi FastAPI/Next.js.
Tidak ada API recognition, tabel, index persisten, OCR, fusion atau UI pada task ini.
Tidak mengimpor storage/DB/auth aplikasi. Dataset tidak dibaca dari foto privat secara
otomatis. Benchmark tidak mengidentifikasi unit fisik atau menghasilkan VERIFIED.

## Dataset dan manifest v1

Simpan dataset privat di luar Git; `data/recognition-eval/` di-ignore. Jangan menaruh foto
aset asli, EXIF, identifier, token, path privat atau prediction per-image di laporan Git.
Gunakan model ID pseudonim, bukan serial/Asset ID. Bukti persetujuan penggunaan foto dan
lisensi dicatat pada sumber dataset lokal. Lisensi kode encoder tidak otomatis menentukan
hak atas data latih/foto; review provenance weight dan dataset sebelum penggunaan bisnis.

`manifest.json` berbentuk objek dengan tepat empat field: `schema_version: 1`,
`dataset_id` (token 1–100 karakter), `synthetic` (boolean), dan `samples` (1–2000 item).
Setiap item mempunyai tepat field berikut:

| Field | Isi |
|---|---|
| id | Token unik, bukan identifier unit asli |
| path | Path POSIX relatif di bawah dataset root; tanpa URL, absolute, traversal atau symlink keluar |
| sha256 | SHA-256 lowercase 64 digit dari bytes foto |
| model_id | Label model katalog pseudonim; null hanya untuk unknown |
| split | reference, calibration, test, unknown_calibration, unknown_test |
| capture_group | Grup unit/burst/sesi asal; seluruh turunannya harus dalam satu split |
| source | Provenance dan izin penggunaan, bukan secret/identifier unit |
| license | Lisensi/izin foto yang dapat ditinjau |
| captured_at | ISO 8601 dengan zona waktu |

Contoh satu baris (hash diganti dengan hash file aktual):

```json
{"id":"sample-001","path":"reference/model-a/photo-01.jpg","sha256":"REPLACE_WITH_SHA256",
 "model_id":"model-a","split":"reference","capture_group":"capture-a-01",
 "source":"approved local capture batch 1","license":"internal evaluation permission",
 "captured_at":"2026-10-19T08:00:00+08:00"}
```

Semua lima split wajib ada; tiap model known wajib punya reference, calibration dan test.
Unknown bukan label model known dan tidak berada dalam referensi. Label unknown harus
benar-benar out-of-catalog berdasarkan review manusia; validator tidak bisa membuktikannya
dari piksel. Reference minimum 5–15 foto per model dari berbagai sudut; test 3–5 foto baru
terpisah. Gunakan set kalibrasi known/unknown tambahan, bukan foto test untuk memilih threshold.

Jangan memecah burst, crop, re-encode atau augmentasi foto yang sama ke split berbeda.
Validator memeriksa ID/path/byte hash unik, SHA-256 aktual, capture_group, decoded RGB hash
setelah EXIF transpose dan dHash64 dengan Hamming distance <=4 antar split. Near-duplicate
heuristic bisa false-positive atau melewatkan rotasi/crop/kemiripan semantik: review manual
unit/sesi tetap wajib; jangan menghapus guard agar angka akurasi terlihat lebih baik.
Hanya PNG/JPEG decoded satu frame, 10 MiB/file, sisi 64–4096, maksimum 16 juta piksel,
manifest maksimum 2 MiB. Image decoder tidak memanggil URL atau layanan eksternal.

## Protokol dan metrik

- Ekstraksi feature sebelum classifier, average pooling existing encoder, L2 normalization.
  CPU saja, eval/inference mode, batch1, dua thread intra-op/satu inter-op, seed0 dan deterministic.
  EXIF transpose + RGB, lalu transform resmi weights (resize/crop/normalisasi).
- Referensi dinilai dengan cosine; skor model adalah maksimum skor foto referensi model itu.
  Model diurutkan skor descending, tie model_id ascending. Top-3 berisi model unik,
  bukan tiga foto dari model yang sama. Tidak membangun index aplikasi Task 3-02.
- Threshold ditentukan **hanya** dari known dan unknown calibration: maksimalkan rata-rata
  known acceptance dan unknown rejection; tie pilih threshold lebih tinggi. Accept jika
  similarity >= threshold. Threshold bisa sedikit >1 untuk kasus semua skor identik,
  sehingga seluruhnya ditolak. Nilai bukan probabilitas atau confidence terkalibrasi.
- Top-1/top-3 raw retrieval memakai held-out known test; juga dilaporkan correct-known
  accepted rate agar rejection tidak tersamarkan. Per-model metrics dan confusion disertakan.
- Unknown dianggap kelas positif: TP unknown ditolak, FP known ditolak, FN unknown diterima.
  Precision=TP/(TP+FP), recall=TP/(TP+FN), F1; denominator nol menghasilkan null.
  False accept unknown, false reject known dan wrong accepted known dilaporkan terpisah.
- Tidak memakai test untuk memilih threshold/encoder secara otomatis. Bandingkan laporan
  dua kandidat; jika test menjadi dasar pemilihan, kumpulkan held-out final baru sebelum
  klaim rilis. Tidak ada encoder produksi terpilih otomatis.
- `top3_go_no_go` hanya target top-3 >=90% pada dataset layak, bukan persetujuan produksi.
  Guard kelayakan: non-synthetic, >=4 model (top-3 pada <=3 model trivial), per model >=5
  reference/2 calibration/3 test, unknown calibration/test masing-masing >=3. Ini minimum
  harness, bukan jaminan representativitas atau cukupnya ukuran statistik. Evaluasi FPR,
  kesulitan unknown, jumlah unit, pencahayaan dan variasi kamera tetap diperlukan.
- Latency p50/p95 menggunakan percentile linear NumPy atas seluruh sample x3 repeat;
  warmup5 tidak termasuk. Tersedia decode+preprocess, encoder, search, dan end-to-end.
  Cold model load terpisah. Network/upload/DB/validasi manifest tidak dihitung. Peak RSS
  per proses Linux mencakup import, validasi, model dan buffer; bukan VRAM atau RAM host.
  Jalankan kandidat dalam proses terpisah tanpa suite berat bersamaan.

## Menjalankan

Dari root repo Ubuntu WSL2:

```bash
bash infra/check-recognition-eval.sh
# Build mengunduh library CPU dan weights publik; tidak mengunggah foto/data.
# Berikutnya semua test/benchmark memakai --network none.
mkdir -p data/recognition-eval
# Fixture sintetis baru; tidak overwrite direktori existing:
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/data/recognition-eval,dst=/work" \
  assetvision-recognition-eval:3-01 synthetic /work/synthetic-v1
bash infra/benchmark-recognition.sh \
  data/recognition-eval/synthetic-v1 data/recognition-eval/baseline-v1
# Dataset nyata berizin: siapkan manifest sendiri, gunakan direktori laporan BARU.
bash infra/benchmark-recognition.sh /absolute/private-dataset /absolute/new-report
```

Runner memakai container CPU2/mem2GiB, non-root, read-only filesystem dan dataset, tmpfs,
cap-drop ALL, no-new-privileges, network none; hanya direktori laporan baru writable.
Tidak menjalankan Compose/up/migrate/seed dan tidak menerima DATABASE_URL/.env. Weights sudah
ada di image; cache hilang/hash salah membuat benchmark gagal, bukan download diam-diam.
`prepare-weights` adalah satu-satunya subcommand dengan download publik eksplisit dan hanya
menyediakan dua URL dari enum torchvision. Perintah validate/synthetic tidak mengimpor torch.
Dua JSON report menyertakan manifest/hash weight penuh, versi library/preprocess, jumlah split,
prediksi per sample, threshold, metrik, CPU/platform/thread/RSS dan latency. File output
existing ditolak, dataset dicek ulang setelah pengukuran, error normal tidak mencetak EXIF/path.
Log/data privat tetap lokal. Simpan ringkasan agregat yang telah diperiksa di dokumen sprint.

## Kandidat dan sumber primer

- [MobileNetV3 Small](https://docs.pytorch.org/vision/0.25/models/generated/torchvision.models.mobilenet_v3_small.html), IMAGENET1K_V1, feature dimension576.
- [ShuffleNet V2 0.5x](https://docs.pytorch.org/vision/0.25/models/generated/torchvision.models.shufflenet_v2_x0_5.html), IMAGENET1K_V1, feature dimension1024.
- [Pasangan versi CPU resmi](https://pytorch.org/get-started/previous-versions/): PyTorch2.10.0/torchvision0.25.0.
- [Lisensi kode torchvision](https://github.com/pytorch/vision/blob/v0.25.0/LICENSE).

ImageNet classification accuracy dari dokumentasi bukan accuracy SKU perangkat lokal.
Hasil sintetis hanya pemeriksaan eksekusi/latency lingkungan ini; NO_GO dan pilihan encoder
harus DEFERRED sampai dataset perangkat berizin dan validasi representatif tersedia.


## Profil CPU foto nyata yang belum memenuhi split evaluasi

Untuk kumpulan satu model/burst tanpa referensi dan unknown independen, gunakan split
`profile` untuk seluruh item dan subcommand benchmark `--profile-only`. Model label dari
pemilik dataset dicatat sebagai provenance, bukan hasil prediksi. `captured_at: null`
diperbolehkan khusus profil jika waktu pengambilan tidak diketahui; jangan mengganti
mtime file sebagai waktu capture. Profil tidak boleh bercampur dengan lima split evaluasi.

Manifest profil dapat diletakkan terpisah dari folder foto agar sumber tidak diubah:

```bash
bash infra/benchmark-recognition.sh data/samples/grandstream-wp810 \
  data/recognition-eval/wp810-run-v1 data/recognition-eval/wp810-profile-v1/manifest.json
```

Argumen ketiga mengaktifkan profile-only dan mount manifest read-only tersendiri. Tidak
membuat referensi/index dari foto itu dan tidak menilai top-k/unknown; metrics dan threshold
null, selection_eligible false, NO_GO. Latency tidak mencakup search (reference_count0).
Output hanya untuk membandingkan footprint/latency enam foto nyata, bukan akurasi perangkat.
Folder asli dan semua sidecar dipertahankan; `data/samples/` di-ignore. Dataset evaluasi riil
masih memerlukan beberapa model, reference/calibration/test independen dan unknown berizin.

`TORCH_HOME=/opt/weights` adalah cache weights internal image. Runner menetapkan
`TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor-eval` pada tmpfs agar import PyTorch bekerja
untuk UID host yang tidak terdaftar di passwd container. Ini konfigurasi tool-only, bukan
variabel .env aplikasi, tidak mengaktifkan torch.compile atau persistent cache.

Build memakai Dockerfile.dockerignore khusus evaluasi untuk membatasi context ke source
harness dan requirements; .env, foto, dataset, .git dan aplikasi tidak ikut context/image.
Mekanisme: [Dockerfile-specific ignore](https://docs.docker.com/build/concepts/context/#filename-and-location).
