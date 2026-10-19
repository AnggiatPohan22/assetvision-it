# Sprint 3-01 — Evaluation harness dan baseline CPU

Tanggal: 19 Oktober 2026 (Asia/Makassar).
Status: implementasi harness, pengujian, benchmark dua encoder CPU dan laporan teknis selesai.
**Go/no-go pemilihan encoder: NO_GO / DEFERRED** karena dataset nyata belum memiliki split
reference/calibration/test/unknown independen. Tidak mengklaim accuracy SKU dari fixture.
Scope hanya3-01. Task3-02 tidak dimulai. Commit lokal diotorisasi terpisah setelah review akhir; tidak push.

## Review hasil Sprint 2 dan keadaan awal

Working tree awal bersih pada main/origin/main `3c4adb975741a3b36c8e074c6914a599facf347e`.
Lima commit Sprint2 sudah tersinkron: fdbc3a7 (hierarchy), b150f8a (asset location),
767c368 (movement), d3a2b89 (timeline/observations), 3c4adb9 (frontend/UAT).
AGENTS.md, README, dokumen Sprint3, arsitektur/bisnis, pola test/Docker dan laporan2-05
penutupan ditinjau. MCP list_projects dicoba; hanya payload-cms-villa terindeks sehingga
sumber lokal dipakai. Memori membantu workflow/isolasi, bukan bukti status data atau tes.

Sprint2 memiliki official location/version, movement atomik dengan RBAC dan retensi,
observasi evidence-only serta timeline read-only. Lokasi bukan identitas unik dan tidak
boleh menjadi dasar VERIFIED. Tidak mengubah alur tersebut. Bukti predecessor617 SQLite,
639 PG, frontend78 dan smoke34 berasal dari Sprint2; tidak diklaim sebagai suite penuh ulang
Task3-01. Head database tetap0009_observations; foto referensi development kosong.

Rencana: snapshot read-only → manifest/leakage dan metrik → image evaluasi CPU terpisah →
unit/negative tests dan regresi existing → dua benchmark → verifikasi preservasi → laporan.
Tidak ada alasan menambah schema/API/index/adapter runtime/UI untuk harness ini.

## Implementasi dan berkas

| Berkas | Perubahan |
|---|---|
| tools/recognition_eval/manifest.py | Dataclass typed, manifest/provenance, bounded local images, split/group/byte/decoded/dHash leakage guards |
| tools/recognition_eval/metrics.py | L2/model ranking, threshold calibration-only, top1/top3, unknown P/R/F1/FPR dan confusion |
| tools/recognition_eval/torch_cpu.py | Runner benchmark-only dua pretrained feature extractor CPU, metadata weights/preprocess, latency/RSS |
| tools/recognition_eval/synthetic.py | Fixture52 gambar geometri baru, deterministic, tidak overwrite |
| tools/recognition_eval/__main__.py, __init__.py | CLI validate/synthetic/prepare-weights/benchmark, output eksklusif |
| tools/recognition_eval/tests | Unittest manifest, metrics, profile gate, offline weights/CLI/resource guards |
| infra/recognition-eval/Dockerfile, Dockerfile.dockerignore, requirements.txt, requirements.lock | Image evaluasi non-root terpisah; CPU-only/pinned environment |
| infra/check-recognition-eval.sh | Build eksplisit + unittest network none/read-only tanpa DB |
| infra/benchmark-recognition.sh | Proses kandidat serial CPU2/mem2GiB, dataset read-only, laporan baru saja writable |
| .gitignore | Foto nyata data/samples dan dataset/hasil lokal data/recognition-eval tetap di luar Git |
| README, ARCHITECTURE, TESTING, RECOGNITION_EVALUATION | Workflow/protokol/batas dan perintah reproduksi |
| Sprint3 status, laporan ini dan SPRINT_3_01_BASELINE.json | Bukti agregat dan keputusan NO_GO tanpa foto/prediksi per-image privat |

Tidak ada perubahan apps/api, apps/web, migrations, compose, .env atau dependency runtime.
Tidak ada automatic upload ke pihak ketiga, Ollama, VLM, GPU, paid API, OCR, fusion atau UI.
Feature extraction dalam runner adalah eksperimen Task3-01; tidak membangun index/rebuild
referensi aplikasi atau endpoint model candidates Task3-02. Vektor hanya ada di memori.

## Dataset dan cara mencegah klaim keliru

Pengguna memberikan `data/samples/grandstream-wp810`: enam JPEG, dua900×1600 dan empat1600×900.
Enam sidecar Zone.Identifier dibiarkan utuh. Foto tidak disalin/diubah atau dimasukkan Git,
tidak diberi label model hasil AI; grandstream-wp810 adalah label folder dari pengguna.
Waktu capture dan independensi unit/burst belum diketahui. Manifest privat menggunakan
capture_group yang sama, split profile dan captured_at=null, bukan mengarang waktu capture.
Hak penggunaan downstream belum dinilai; sumber user-authorized untuk evaluasi lokal ini.

Enam foto satu model belum memenuhi minimum5–15 reference +3–5 held-out test **ditambah**
kalibrasi independen dan unknown out-of-catalog. Memecahnya secara acak akan memberi klaim
lemah; top3 pada satu model juga trivial. Karena itu profil asli menghasilkan metrics=null,
threshold=null, dataset_selection_eligible=false dan NO_GO, tanpa reference search.

Fixture sintetis52 gambar terdiri atas empat label geometri known: reference20 (5/model),
calibration8 (2/model), test12 (3/model); unknown calibration6 dan unknown test6. Seluruh
file/group/hash berbeda lintas split; pemeriksaan decoded/dHash dilakukan. Fixture bukan
foto perangkat, bukan katalog/asset/seed development, dan tidak menjadi dasar pemilihan.

Manifest default mensyaratkan kelima split evaluasi lengkap. Profile adalah mode terpisah,
tidak boleh bercampur. Validasi mencakup SHA aktual, batas file10MiB/dimensi64–4096/16Mpix,
JPEG/PNG satu frame, no traversal/absolute/URL/symlink keluar, unique id/path/bytes,
capture_group dan decoded RGB/dHash64 (Hamming<=4) lintas split. Guard heuristic bukan
jaminan seluruh crop/rotasi/near-duplicate terdeteksi; review sumber/unit/sesi tetap wajib.

## Protokol pengukuran aktual

Dua kandidat: torchvision MobileNetV3 Small IMAGENET1K_V1 (feature576) dan ShuffleNetV2 0.5x
IMAGENET1K_V1 (feature1024). CPU-only PyTorch2.10.0+cpu/torchvision0.25.0+cpu, NumPy2.2.4,
Pillow13.0.0, Python3.12. CPU AMD Ryzen5 5600H with Radeon Graphics, Linux WSL2. Cgroup nyata
cpu.max=200000/100000 (2CPU) dan memory.max=2147483648 (2GiB). Tidak memakai RTX/CUDA.
Library/weights publik diunduh eksplisit saat build; inference/test network none.

Tiap encoder menggunakan proses/container baru, tidak bersamaan dengan tes regresi berat.
Batch1, intra-op2/inter-op1, eval/inference mode dan seed0; warmup5 tidak masuk latency.
Foto ditranspose EXIF, RGB, transform weights resize256/center crop224, normalisasi ImageNet;
feature sebelum classifier di-L2 normalize. Model score=max cosine referensi per model,
tie model_id ascending. Skor bukan confidence/probability. Tidak mengidentifikasi unit.

Masing-masing sample diukur3 kali: sintetis156 pengukuran/kandidat, nyata18/kandidat.
Latency p50/p95 memakai percentile linear. End-to-end mencakup decode/preprocess+encoder
+search pada sintetis; profil nyata tanpa search. Manifest validation, download, API/upload,
DB dan import library tidak termasuk. Kolom cold_model_load_ms mengukur konstruksi/model
state load setelah checksum cache, **bukan** klaim cold disk/boot perangkat. Peak RSS adalah
proses Linux termasuk import/validasi/model/buffer, bukan total RAM host atau VRAM.
Tidak mengklaim benchmark beban, SLA, seluruh kamera atau confidence interval statistik.

Threshold dipilih hanya dari known/unknown calibration untuk balanced acceptance/rejection,
tie konservatif threshold lebih tinggi. Test tidak menala threshold. Rejection positif untuk
unknown precision/recall; false accept unknown dan false reject known dipisahkan. Null berarti
denominator tidak terdefinisi, bukan0. Rincian formula, minimum kelayakan dan sumber primer
weights ada di ../RECOGNITION_EVALUATION.md. Hash weights/preprocess/manifest dan versi detail
serta confusion agregat dicatat di SPRINT_3_01_BASELINE.json.

## Hasil benchmark nyata — enam foto WP810, latency saja

| Kandidat | Decode/preprocess p50/p95 ms | Encoder p50/p95 ms | End-to-end p50/p95 ms | Peak RSS MiB |
|---|---:|---:|---:|---:|
| MobileNetV3 Small |17.34 /17.94|6.64 /7.20|23.93 /24.88|342.09|
| ShuffleNetV2 0.5x |25.39 /34.05|8.76 /9.45|34.07 /43.34|333.89|

Accuracy top1/top3, unknown precision/recall/FPR dan threshold untuk foto nyata **tidak tersedia**.
MobileNet lebih cepat pada run kecil ini; ini hanya petunjuk footprint/latency, bukan pilihan
encoder untuk recognition perangkat. Perbedaan preprocessing juga terkena scheduling/cache
host; pengukuran kecil ini tidak menjamin urutan performa pada workload lain.

## Hasil fixture sintetis — hanya validasi harness

| Kandidat |Top1/Top3|Unknown precision/recall|Unknown false accept|Known false reject|Threshold|E2E p50/p95 ms|RSS MiB|
|---|---:|---:|---:|---:|---:|---:|---:|
|MobileNetV3 Small|100% /100%|100% /66.67%|33.33%|0%|0.893219|8.63 /14.19|329.71|
|ShuffleNetV2 0.5x|100% /100%|100% /83.33%|16.67%|0%|0.918335|8.67 /11.73|321.05|

Denominator held-out: known12 dan unknown6. MobileNet menolak4/6 unknown, ShuffleNet5/6.
Tidak ada wrong-known accepted pada fixture ini. Target top3>=90% tidak boleh dianggap
tercapai untuk perangkat nyata dari angka geometri100%; guard synthetic memaksa NO_GO.
Threshold ini hanya untuk fixture geometri, **bukan** konfigurasi produksi atau Task3-02.

## Pengujian dan hasil

- Harness final: **22 tests passed**, 4.156 detik pada pemeriksaan final context (run sebelumnya9.562 detik), network none/read-only. 19 tes awal lulus;
  ditambah3 tes missing/corrupt cached weights (download tidak boleh dipanggil), batas resource
  sebelum loading serta CLI tidak overwrite laporan. Ini hasil akhir, bukan asumsi.
- Ruff tools: **All checks passed**, format selesai; bash syntax dua runner lulus.
- Regresi backend Sprint2 pada SQLite: **207 passed,15 skipped** (117.28detik), mencakup
  hierarchy/placement/movement/observation API dan guard migration.15 skip adalah tes lock/race
  PostgreSQL-only. Tidak mengklaim menjalankan ulang PG639 atau seluruh SQLite617 di task ini;
  kode/schema aplikasi tidak berubah dan suite PostgreSQL penuh terakhir sudah lulus Sprint2.
- Frontend existing: lint/TypeScript dan **78 passed,0 failed/skipped** (8315.18ms), exit0.
- Empat run benchmark (dua kandidat × sintetis/nyata) exit0. Laporan JSON finite/parsable,
  synthetic NO_GO dan real metrics/threshold null. Source core sama dengan image teruji.
- Runtime read-only probes: ready200; inbox observation401; /assets,/locations,/movements
  redirect307 ke/login. Alembic current0009_observations(head); check No new upgrade operations.

Iterasi yang ditemukan/diperbaiki: Ruff format/import/line length dan bound loop lambdas;
UID tool mount perlu UID pemilik untuk formatting. WSL sempat timeout selama layer unpack,
kemudian pulih tanpa restart/recreate service. Percobaan benchmark pertama gagal sebelum
inference karena UIDhost1000 tidak ada di passwd container saat PyTorch mencari cache.
Runner kini menetapkan TORCHINDUCTOR_CACHE_DIR pada tmpfs; tidak mengubah user/credential
atau mengaktifkan compile. Run final empat kandidat berhasil; direktori percobaan kosong
lama dipertahankan dan laporan baru memakai nama berbeda, tanpa overwrite bukti.

## Perintah yang dijalankan

Dari Ubuntu WSL2 root repo; source code disusun melalui writer WSL. Output tes panjang /tmp.

```bash
git status --short --branch
git log -6 --oneline
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py > /tmp/av-sprint3-01-before.json
docker build -f infra/recognition-eval/Dockerfile -t assetvision-recognition-eval:3-01 .
docker compose --profile test run --rm --no-deps web-check npm run check
docker compose --profile test run --rm --no-deps api-test python -m pytest -q tests/test_locations.py tests/test_asset_locations.py tests/test_movements.py tests/test_observations.py
# Ruff format/check tools: api-test, --network none, bind /src/tools, config /app/pyproject.toml.
bash infra/check-recognition-eval.sh
# Fixture generated explicitly in ignored directory via container synthetic subcommand.
bash infra/benchmark-recognition.sh data/recognition-eval/synthetic-v1 data/recognition-eval/synthetic-run-v2
bash infra/benchmark-recognition.sh data/samples/grandstream-wp810 data/recognition-eval/wp810-run-v1 data/recognition-eval/wp810-profile-v1/manifest.json
docker compose exec -T api alembic current
docker compose exec -T api alembic check
python3 /tmp/av-20261019-2-05-probe.py
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py > /tmp/av-sprint3-01-after.json
cmp /tmp/av-sprint3-01-before.json /tmp/av-sprint3-01-after.json
bash -n infra/check-recognition-eval.sh infra/benchmark-recognition.sh
git diff --check
docker compose ps
```

Log final: /tmp/av-sprint3-01-final-context-check.log (22 tes), complete-harness-check.log, api-regression.log, web-check.log,
benchmark-final.log (tiga terakhir memakai prefix /tmp/av-sprint3-01-). Source/per-image JSON
asli ada di data/recognition-eval yang di-ignore. Ringkasan Git hanya agregat yang ditinjau,
tanpa foto/EXIF/raw identifiers. Manifest profil dibuat lokal tanpa mengubah folder foto.

## Preservasi data existing

Fingerprint read-only sebelum dan sesudah **identik byte** (`cmp` exit0), mencakup semua
baris/kolom/timestamp/version/PostGIS/Alembic dan file storage, tanpa pengecualian. Tidak ada
login/seed/backfill/placement/movement/review atau migrasi development. API/web/db tidak
recreate; seluruhnya healthy dengan DB internal saja dan API/web bind127.0.0.1.

Hash12 berkas asli pengguna (6JPEG+6sidecar) identik sebelum/sesudah. Tidak menghapus metadata
atau mengubah resolusi sumber; preprocessing hanya memori. Foto dan data evaluasi tidak
ter-stage; .gitignore menutup keduanya. Tidak ada database dump/foto/weights/secret di diff.

## Keputusan dan batas tindak lanjut

**Tidak memilih encoder atau threshold produksi.** Profil CPU menunjukkan dua kandidat dapat
dijalankan tanpa GPU di lingkungan ini, tetapi akurasi real/unknown rejection belum terbukti.
Siapkan beberapa model katalog, foto reference/calibration/test independen dari unit/sesi,
serta unknown out-of-catalog; catat izin/provenance dan review near-duplicate. Gunakan harness
ini untuk benchmark nyata lanjutan, lalu review target top3/FPR sebelum keputusan encoder.
Ini prasyarat data untuk melengkapi go/no-go3-01, bukan izin memulai3-02. Tidak ada task
berikutnya atau push; commit lokal mengikuti review penutupan di bawah.


## Review diff akhir

23 berkas berubah/baru, seluruhnya Task3-01. Sembilan source Python identik dengan image
yang lulus22 tes; hash tersimpan pada agregat baseline. Foto, weights, DB/dump dan .env
bukan bagian diff. Dockerfile.dockerignore khusus evaluasi membatasi build context ke tool
source dan requirements saja. Pada akhir implementasi index kosong; tidak push atau mulai3-02.


## Review penutupan dan commit lokal

Atas permintaan pengguna pada19 Oktober2026, diff akhir seluruh23 berkas ditinjau sebelum
commit. Tidak ditemukan temuan penghalang. Pemeriksaan meliputi manifest/provenance,
split/group/hash/visual leakage, metrik dan denominator, threshold calibration-only,
synthetic/profile NO_GO, ekstraksi CPU/version/preprocess, offline weights, batas resource,
read-only dataset, output eksklusif, pemisahan dependensi serta konsistensi laporan.

Tidak ada perubahan kode setelah pengujian. Hash sembilan source Python identik dengan
image evaluasi dan manifest baseline. Hash keempat JSON benchmark asli cocok dengan agregat;
profile nyata tetap metrics/threshold null dan semua selection gate NO_GO. Log aktual
mengonfirmasi22 tes harness,207 backend/15 skip PostgreSQL-only, serta78 frontend dan
lint/typecheck lulus. Suite/benchmark tidak diulang karena sumber teruji tidak berubah.
Hanya catatan penutupan laporan ini diperbarui.

Fingerprint read-only baru /tmp/av-sprint3-01-commit-review.json identik byte dengan baseline
awal; database/storage tetap utuh tanpa pengecualian. Hash12 foto/sidecar juga identik.
API/web/db healthy; tidak login, seed, migrate, recreate atau mengubah sumber foto.
Bash syntax kedua runner dan git diff --check lulus. Source aplikasi/migration/.env tidak berubah.

Staging menggunakan daftar eksplisit23 berkas, tanpa foto, weights, dataset privat atau dump.
Diff staged diperiksa sebelum commit lokal dengan pesan
`feat: add Sprint 3-01 recognition evaluation harness`.
Tidak push dan Task3-02 tidak dimulai. Pemilihan encoder tetap menunggu dataset nyata lengkap.
