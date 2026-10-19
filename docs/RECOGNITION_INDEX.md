# Embedding index — Task 3-02

Task ini menyediakan adapter encoder CPU opsional, generation index PostgreSQL, rebuild
referensi dan pencarian **model perangkat**. Tidak mengidentifikasi unit fisik, tidak membaca
lokasi untuk inferensi, tidak membuat aset/observasi atau mengubah master. Belum ada endpoint
recognition/route proxy/UI, OCR atau evidence fusion; task berikutnya belum dimulai.

## Batas dari Task 3-01

Benchmark enam foto WP810 membuktikan eksekusi/latency CPU, bukan accuracy SKU atau unknown
rejection. Belum ada encoder/threshold produksi yang dipilih. Tidak ada default encoder atau
threshold di konfigurasi aplikasi. Pemanggil memilih adapter secara eksplisit; tanpa kalibrasi
hasil ranking hanya `UNCERTAIN`. Nilai cosine disebut similarity, bukan confidence/probability.
Threshold fixture sintetis Task3-01 tidak boleh dipromosikan menjadi konfigurasi bisnis.

`ImageEncoder` adalah Protocol dengan EncoderSpec frozen dan encode(image RGB) -> vector.
Default API tidak mengimpor torch/torchvision dan requirements API tetap ringan. Dua adapter
CPU opsional mengikuti kandidat yang sudah diukur: mobilenet_v3_small dan shufflenet_v2_x0_5,
PyTorch2.10.0+cpu/torchvision0.25.0+cpu IMAGENET1K_V1, dimensi576/1024. Weight SHA-256 penuh,
versi library dan fingerprint preprocessing diverifikasi; cache hilang/berubah ditolak tanpa
network/download. Builder memakai weights=None dan torch.load(weights_only=True,CPU).

Decoder memeriksa MIME/magic, byte limit IMAGE_MAX_BYTES existing (maksimum8MiB), satu frame,
sisi maksimum4096, maksimum16 juta pixel, JPEG/PNG/WebP, EXIF transpose dan RGB. Foto katalog
lama yang melampaui batas embedding ditolak saat rebuild, tidak diperkecil/ditimpa diam-diam.
Transform encoder resize/crop/normalisasi sama dengan3-01; tidak re-encode sumber atau menulis
EXIF. Feature di-L2 normalize, dimensi/non-finite/zero vector ditolak. Encode memakai CPU2
thread intra-op, inter-op1 dan inference/eval mode. Tidak menggunakan GPU atau training.

## Data dan versioning

Migration0010_embedding_index hanya menambah:

| Tabel | Isi |
|---|---|
| embedding_indexes | Immutable generation UUID, EncoderSpec (nama/version/weights/preprocess/dimensi), fingerprint sumber, jumlah referensi, kalibrasi opsional, actor/time |
| image_embeddings | Generation FK, current reference FK nullable, snapshot UUID referensi immutable, model FK, hash bytes sumber, vector JSONB dan waktu |
| embedding_index_state | Singleton id1, current generation nullable dan optimistic version (awal1) |

Metadata encoder disimpan sekali pada parent generation, tidak diduplikasi per vector.
PostgreSQL tetap source of truth; SQLite hanya untuk tes. Tidak menambah pgvector, Redis,
queue, cache persistensi lain atau menyimpan base64/foto di database. State awal tidak
memilih encoder atau membangun vektor. Tabel embedding kosong setelah migration.

Generation/history tidak dapat UPDATE/DELETE. SQL guard insert memeriksa relasi/hash/model
sumber dan kapasitas generation. Vector shape/norm/finiteness divalidasi writer dan reader.
Penghapusan foto existing tetap boleh: FK current reference menjadi null, UUID/hash snapshot
serta vector historis tetap utuh. Tidak ada cascade delete histori atau perubahan API foto.
Head hanya berubah dengan version+1 dan non-null current generation. Downgrade menolak
embedding/index yang berisi data; empty migration roundtrip tetap tersedia untuk tes.

## Rebuild atomik

1. ADMIN aktif saja; periksa expected_version dan ambil snapshot katalog dengan satu query.
   Fingerprint mencakup id/version/is_active model (termasuk model tanpa foto/inactive) dan
   metadata seluruh foto. Encode hanya referensi model is_active lokal; tidak mengarsipkan
   model/parent atau menyalin foto dari folder samples secara otomatis.
2. Lepas transaksi sebelum pekerjaan CPU/storage. Baca via StorageProvider existing, cocokkan
   bytes/size/SHA metadata dan validasi/decode gambar. Maksimum2000 referensi eligible, snapshot
   maksimum5000 row. Error satu foto/vector membatalkan seluruh rebuild, tanpa skip diam-diam.
3. Lock head, cek ulang role/status actor, expected_version, fingerprint dan spec encoder.
   Buat generation+seluruh vector+audit, geser pointer/version dalam satu commit. Fail audit,
   stale source/head, FK atau encoder error meninggalkan generation sebelumnya utuh.

Dua rebuild boleh menghitung bersamaan; hanya satu memenangkan CAS atas expected_version yang
sama, lainnya409. Tidak ada auto retry/version bump. CPU tidak menahan lock foto/model atau
head. Perubahan katalog yang sangat dekat setelah pemeriksaan bisa langsung membuat generation
stale; setiap search memeriksa fingerprint sehingga tidak mencampur referensi lama/baru.
Rerun eksplisit selalu membuat generation/audit baru; belum ada incremental reuse/pruning.
Operasi memerlukan session bersih agar tidak commit/rollback perubahan caller yang belum disimpan.

## Query dan keputusan

Semua user aktif dapat membaca via service; rebuild khusus ADMIN. Role/status diambil ulang
dari database, termasuk setelah CPU. CLI adalah alat operator lokal dengan akses DB; actor UUID
untuk attribution/audit, bukan pengganti login browser. HTTP berikutnya wajib memakai session
backend existing, bukan menerima UUID sembarang sebagai autentikasi.

Reader memakai vector persisted dan fingerprint metadata; tidak membaca ulang seluruh file
referensi per query. Checksum bytes sumber diuji saat rebuild. Reader membekukan current
generation/spec, memeriksa fingerprint, jumlah/vector, encode query,
cosine dot terhadap unit vectors, lalu max per model. Ranking model unik, tie similarity:
model UUID ascending; foto pemenang tie memakai snapshot UUID ascending. top_k1–10, default3.
Tidak ada unit/asset ID pada hasil, tidak ada query writes/audit mutasi/master update.

| Kondisi | Hasil |
|---|---|
| Belum ada index / tidak ada foto model aktif | UNKNOWN_MODEL, EMPTY_INDEX / NO_ACTIVE_REFERENCES, tanpa kandidat |
| Index/source stale atau berubah selama query | UNCERTAIN, tanpa kandidat |
| Adapter tidak dikonfigurasi / versinya berbeda | UNCERTAIN, tanpa kandidat |
| Vector/index/policy tidak valid | UNCERTAIN (metadata generation invalid503), tanpa kandidat |
| Tidak ada kalibrasi | UNCERTAIN + top-k similarity informasional, tidak ada threshold |
| Kalibrasi valid, maximum similarity <threshold | UNKNOWN_MODEL, tanpa kandidat |
| Kalibrasi valid, maximum similarity >=threshold | KNOWN_MODEL_CANDIDATE + top-k similarity, bukan identitas unit |

Status known berarti kandidat terbaik melewati threshold, bukan setiap alternatif/top-k
mempunyai confidence terkalibrasi. Reader memeriksa head/fingerprint/encoder kembali setelah
CPU, dan tidak menghasilkan VERIFIED_ASSET/PROBABLE/AMBIGUOUS/CONFLICT unit (Task3-04).
Rebuild baru tanpa report tidak mewarisi threshold generation lama.

## Kalibrasi yang ditinjau ADMIN

Default uncalibrated disengaja. Untuk memasang policy, ADMIN harus memberikan report
**real** dari harness3-01, fingerprint referensi yang ditinjau, reason dan konfirmasi rebuild.
Report synthetic/profile/NO_GO ditolak. Wajib spec encoder/preprocess/dimensi sama, minimal
4 model dengan5 reference/2 calibration/3 test per model dan unknown calibration/test>=3,
metric finite dan target top3>=90%. Mapping model UUID dan jumlah reference harus sama dengan
katalog; fingerprint yang diikat harus tepat sama. Threshold harus finite dalam domain cosine
(termasuk nextafter(1,+inf) untuk reject-all) dan tidak diubah/ditala dari query produksi.
Policy menyimpan hash report kanonis, manifest, encoder dan reference snapshot dalam generation
immutable, dengan actor/time/reason rebuild. Tidak ada API untuk mengedit policy secara diam-diam.

Validator mengecek **isi report yang diajukan**, bukan membuktikan truth label atau independensi
foto yang tidak disertakan report. ADMIN bertanggung jawab memastikan referensi dataset aktual
sama dengan snapshot katalog dan meninjau provenance/split/unknown/FPR. Ini attestation operator,
bukan sertifikasi otomatis. Dataset WP810 dan sintetis existing belum memenuhi gerbang ini.
Tes memakai report buatan dalam DB test saja untuk menguji kontrak; bukan kalibrasi produksi.

## Menjalankan dan konfigurasi tool-only

```bash
# Dari root Ubuntu WSL2; test CPU tidak menyentuh DB/storage development.
bash infra/check-recognition-index.sh
# Optional operator tool; tidak otomatis berjalan pada compose up default:
docker compose -f compose.yaml -f compose.recognition.yaml --profile recognition run --rm --no-deps recognition-index --actor-id ADMIN_UUID status
# Review output version dan fingerprint sebelum rebuild eksplisit:
docker compose -f compose.yaml -f compose.recognition.yaml --profile recognition run --rm --no-deps recognition-index --actor-id ADMIN_UUID rebuild --encoder mobilenet_v3_small --expected-version VERSION_DARI_STATUS --reason "Alasan operator" --confirm-rebuild
```

Contoh encoder bukan pilihan produksi/default. Ganti UUID/version/encoder setelah review nyata.
Script check membangun image evaluasi3-01 (cache weights publik), kemudian image CLI3-02 yang
terpisah dari API default. CPU integration tests network none/mem2GiB/CPU2/tmpfs/readonly;
Compose operator hanya network internal DB, storage referensi mounted read-only, tanpa port,
cap_drop ALL/no-new-privileges. Dockerfile-specific ignore mengecualikan .env/foto/data/.git.
Tidak mount folder samples. SOURCE/storage/query tidak pernah diunggah ke luar.

Query CLI: `search --encoder NAMA --image /input/query.jpg --mime-type image/jpeg --top-k 3`;
mount input tambahan read-only secara eksplisit bila digunakan. Kalibrasi:
`rebuild ... --calibration-report /input/report.json --calibration-reference-fingerprint HASH`.
File report maksimal2MiB, query maksimalIMAGE_MAX_BYTES+1 saat pembacaan bounded. Log normal
hanya output JSON kandidat/spec atau penolakan umum, bukan raw bytes, EXIF atau credential.

Tidak ada environment recognition baru pada .env aplikasi. Image mewarisi TORCH_HOME=/opt/weights
(cache build publik) dan menetapkan TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor-index pada tmpfs;
ini tidak mengaktifkan torch.compile. --weights-root menunjuk cache lokal, tidak menerima URL.
Connection/auth/image settings memakai konfigurasi API existing. Runtime recognition belum
punya SLA/rate limit HTTP karena endpoint belum dibuat; jangan mempublikasikan CLI sebagai server.
