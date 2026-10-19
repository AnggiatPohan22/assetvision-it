# OCR label lokal — Task 3-03

Task ini menyediakan service Python transient, adapter PaddleOCR CPU opsional dan CLI lokal.
Belum ada endpoint `/api/v1/recognition/ocr`, UI koreksi, persistence ocr_results atau survey,
evidence fusion, pencarian unit maupun review approval. Bagian itu menunggu task berikutnya.
Tidak ada migration, penambahan IdentifierSource ke master, backfill atau mutasi data existing.

## Evidence dan parsing

`read_label` menerima bytes JPEG/PNG/WebP, engine opsional dan ManualCorrection opsional.
Decoder Task3-02 dipakai bersama: MIME/magic, single frame, EXIF orientation ke RGB,
8MiB, sisi4096 dan16Mpixel. Argumen byte limit eksplisit membuat OCR lokal tidak memerlukan
JWT/database settings; pemanggil embedding existing tetap memakai IMAGE_MAX_BYTES existing.
Tidak menulis ulang foto, menyimpan base64/EXIF, mengirim foto ke cloud atau mencatat teks label.

Hasil frozen menyimpan SHA256 foto asli, timestamp UTC, engine/model fingerprint, parser
version, raw_text persis gabungan line OCR, text/score per line dan kandidat dengan line_indices.
Score adalah skor pembacaan engine, bukan probabilitas identitas. Batas128line,512char/line,
16384char total, score finite0..1. Invalid output tidak dipromosikan menjadi identifier.
Semua hasil `requires_review=true`; status hanya REVIEW_REQUIRED atau MANUAL_REQUIRED.
Tidak ada asset_id, VERIFIED_ASSET, pembaruan master atau otomatisasi berdasarkan lokasi.

Parser hanya mengambil field berlabel eksplisit SN/S/N/Serial, MAC, LAN MAC, WLAN/Wi-Fi MAC,
BSSID atau Model. Field berlabel yang berdiri sendiri boleh memakai line berikutnya jika
line itu bukan field baru. Nilai yang konflik tetap terpisah. Tidak menebak SN dari angka
barcode, merek dari logo atau identifier tanpa label. Serial case/punctuation dipertahankan
sesuai normalisasi master existing. SN placeholder UNKNOWN/N/A/NA/- ditolak.
SN berisi whitespace/damage marker/non-ASCII ditolak sebagai kandidat; teks aslinya tetap ada.
O/0/I/l/1 tidak pernah diperbaiki otomatis; kandidat OCR diberi CHECK_AMBIGUOUS_CHARACTERS.

MAC menerima12hex, colon, hyphen dan dotted, lalu canonical uppercase colon menggunakan
normalizer master existing. Tidak mengubah O menjadi0 atau mengisi digit hilang. MAC generik
bertanda MAC_TYPE_UNSPECIFIED, tidak diasumsikan MAC_LAN, MAC_WLAN atau BSSID. Broadcast,
zero dan multicast bertanda NON_DEVICE_MAC_ADDRESS. BSSID tetap terpisah dari MAC perangkat.
Skor OCR<0.85 diberi LOW_OCR_SCORE: ini heuristik review, bukan threshold akurasi terkalibrasi.
Semua kandidat, termasuk manual dan score tinggi, tetap memerlukan pemeriksaan manusia.

`corrected_text` disimpan terpisah dari raw_text/lines/ocr_candidates. manual_candidates
menyimpan source MANUAL dan tidak diberi skor OCR/verified. Teks kosong boleh menandakan label
tidak terbaca; tidak membuat klaim palsu. Tanpa engine, timeout, model tidak tersedia atau
pembacaan tanpa identifier: operator dapat memberi koreksi manual, atau mengambil foto baru.
DTO ini transient, belum audit reviewer persisten; jangan menganggap koreksi sebagai approval.

## Adapter CPU opsional

PaddleOCR3.2.0, PaddlePaddle3.2.0, PaddleX3.2.1; deteksi PP-OCRv4_mobile_det dan recognition
English en_PP-OCRv4_mobile_rec. Model ini dipakai untuk teks label Latin/digit, bukan classifier
model/unit perangkat. Runtime API default tidak mendapat dependensi Paddle atau torch baru.
Image Python3.12 terpisah, CPU2, mem2GiB, tanpa GPU/port/jaringan/database/storage development.
Paket transitive dipin pada infra/ocr/requirements.lock setelah environment berhasil diverifikasi.

Enam file model dipin SHA256 di app/ocr_weights.json; preparation mengunduh public weights
resmi saat build eksplisit saja. Ekstraksi hanya tiga filename tetap per model, bukan path dari
tar. Runtime memeriksa file reguler, ukuran, direktori/symlink, checksum dan versi dependency.
Tidak memakai fallback remote/hub; model hilang/corrupt/version mismatch berarti manual.
Orientation classifier/unwarping/textline orientation dinonaktifkan agar tidak auto-download
model tambahan. RGB dikonversi BGR sesuai pipeline; detector side max960, dua CPU threads,
MKLDNN off. Bahasa/model/transform/version dicatat pada engine_version/fingerprint.

Inference berjalan dalam child Python per foto. Parent memakai subprocess timeout30detik
(default;1..120), lalu kill+wait child jika lewat deadline. Stdout/stderr engine dibuang,
JSON hasil dibatasi128KiB dan divalidasi kembali. Temporary files dibersihkan; gambar tidak
menjadi argumen shell/path dari pengguna. Batas memory/CPU diberikan container. Tidak ada
worker daemon, queue atau background inference. Init per foto menambah cold-start latency.

## Operasional

Jalankan dari root Ubuntu WSL2:

```bash
bash infra/check-ocr.sh
docker compose -f compose.yaml -f compose.ocr.yaml --profile ocr config --quiet
docker compose -f compose.yaml -f compose.ocr.yaml --profile ocr run --rm --no-deps ocr --help
```

Gunakan direktori input lokal eksplisit secara read-only. Output berisi teks label/identifier
privat, bukan log publik; jika menyimpannya, gunakan lokasi ignored data/private dan izin lokal.
Contoh berikut membaca label milik operator, tidak memasukkan data ke database:

```bash
docker run --rm --network none --read-only --tmpfs /tmp:size=256m \
  --cpus 2 --memory 2g --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
  -v /ABSOLUTE/PRIVATE/LABELS:/input:ro assetvision-ocr:3-03 \
  --engine paddle --image /input/label.png --mime-type image/png
# Koreksi file UTF-8: field berlabel, newline LF; maksimal16384char/128line/512char per line.
docker run --rm --network none --read-only --tmpfs /tmp:size=256m \
  --cpus 2 --memory 2g --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
  -v /ABSOLUTE/PRIVATE/LABELS:/input:ro assetvision-ocr:3-03 \
  --engine manual --correction-file /input/correction.txt
```

Tambahkan --correction-file pada --engine paddle untuk mempertahankan raw OCR dan hasil koreksi
bersama. --engine wajib eksplisit; --models-root default/opt/ocr-models, --timeout-seconds30.
Tidak ada env baru pada .env aplikasi. Container ENV internal: HOME=/tmp/ocr-home,
OMP_NUM_THREADS/OPENBLAS_NUM_THREADS=2 dan PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True;
network none adalah pembatas operasional jaringan. CLI tidak mengautentikasi user browser;
operator adalah pemilik akses filesystem lokal, bukan endpoint terbuka. Error input fatal exit2
mengandung pesan generik, tanpa path/text/traceback. Kegagalan engine normal menghasilkan
MANUAL_REQUIRED/hasil koreksi dan exit0; bukan keberhasilan membaca label.

## Bukti dan batas

Unit tests menguji label rusak/buram (fixture/fake reading), placeholder, perbedaan karakter,
MAC/type/context, raw/correction, output invalid, MIME/dimensi, ukuran, subprocess timeout yang
benar-benar membunuh child, dan kegagalan engine/model. CPU suite memakai weights nyata dan
label generated dengan font terkontrol, termasuk versi, blur, corrupt/symlink dan CLI aktual.
Ini membuktikan integrasi, bukan akurasi label perangkat nyata atau kelayakan semua font/SKU.
Belum ada dataset label nyata held-out/ground truth; gambar WP810 existing tidak diubah atau
diklaim sebagai benchmark OCR. Gate encoder/threshold visual NO_GO3-01 tetap berlaku.
Hasil aktual dan footprint ada di docs/sprints/SPRINT_3_03_REPORT.md.

Referensi resmi untuk adapter/model:
- https://github.com/PaddlePaddle/PaddleOCR/blob/v3.2.0/paddleocr/_pipelines/ocr.py
- https://github.com/PaddlePaddle/PaddleOCR/blob/v3.2.0/docs/version3.x/pipeline_usage/OCR.en.md
- https://github.com/PaddlePaddle/PaddleOCR/blob/v3.2.0/LICENSE

Build cache opsional (bukan env runtime/.env): PIP_FIND_LINKS menunjuk wheel cache operator,
PIP_NO_INDEX=1 menolak index remote jika cache lengkap, dan OCR_BUILD_NETWORK=host dapat
mengakses cache loopback saat build. Default build memakai jaringan Docker default dan PyPI.
Jangan berikan credential dalam URL/cache. Runtime test/inference tetap network none.

OCR_MODEL_ARCHIVE_CACHE_URL opsional hanya saat build menunjuk cache dua archive publik
model. Enam file hasil ekstraksi tetap harus cocok checksum pin; cache tidak mengubah model.
Default kosong memakai sumber resmi. Argumen cache ini bukan env inference atau .env aplikasi.

Hasil final Task 3-03: SQLite748/PG771/frontend78 lulus; empat tes Paddle dan empat regresi
encoder CPU lulus. Pada satu label generated, child Paddle7.726detik/~606MiB max RSS;
image opsional~2.49GiB disk. Ini bukti integrasi, bukan accuracy label perangkat nyata atau
SLA worst-case. Rincian perintah, skip, preservasi dan keterbatasan ada di laporan Task 3-03.
