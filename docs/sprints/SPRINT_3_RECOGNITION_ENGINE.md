# AssetVision IT — Sprint 3: Lightweight Recognition, OCR & Evidence Matching

**Status:** Planned · **Prasyarat:** Sprint 1A, 1B, dan 2 selesai · **Estimasi:** 10–15 hari kerja + waktu evaluasi dataset · **Prioritas:** P0

## Tujuan

Mengenali **kandidat model** perangkat dari foto smartphone tanpa Ollama/VLM besar, mencoba membaca SN/MAC/model dari label, mendukung **perangkat baru yang belum ada katalog**, dan menyusun **kandidat unit fisik berdasarkan bukti** (visual + identifier + lokasi + histori). **Jangan menyamakan pengenalan model dengan identitas unit.**

## Hardware & biaya

- Laptop Windows/WSL2, RAM 16 GB, RTX 3050 VRAM 4 GB.
- Mulai **CPU-first** dengan ONNX Runtime atau PyTorch CPU untuk prototipe; GPU opsional setelah benchmark.
- Tidak ada ketergantungan Ollama, model multimodal besar, atau API berbayar.
- OCR: PaddleOCR CPU sebagai adapter utama jika footprint memadai; Tesseract atau manual entry fallback.
- Untuk katalog kecil, cosine similarity via NumPy sudah cukup; `pgvector` **opsional** setelah benchmark.
- **Unknown discovery:** OCR teks/logo/model + kategori umum + hasil pencarian katalog yang diizinkan; cloud vision hanya adapter opt-in setelah review privasi, bukan syarat MVP. Model tidak boleh mengarang merek/model spesifik yang tidak didukung bukti.

## Batas scope

**Termasuk:** image preprocessing, embedding extraction, referensi katalog, top-k similarity, threshold reject UNKNOWN, OCR label, normalisasi SN/MAC, candidate evidence fusion, observasi dan hasil review, evaluation harness, UI minimal upload/hasil.

**Tidak termasuk:** live video frame-by-frame, training detector custom, continuous background camera, integrasi controller Ruijie, otomatis mutasi lokasi, model generatif wajib, atau auto-create asset dari hasil AI.

## Pipeline

```text
Foto perangkat → validasi file → preprocessing → embedding
  → top-k device models + similarity + model_version
  → calibrated reject: KNOWN_CANDIDATE / UNKNOWN / UNCERTAIN

Foto label (opsional) → OCR → kandidat teks → parse SN/MAC/model
  → human correction bila OCR lemah

Model candidates + identifiers + current location + movement history
  → deterministic evidence rules → candidate asset units
  → VERIFIED only with strong unique evidence + explicit review policy
  → PROBABLE / AMBIGUOUS / CONFLICT / UNKNOWN
  → save observation + evidence + reviewer decision
```

**Batasan penting:** skor cosine bukan probabilitas/confidence terkalibrasi. Threshold wajib dipilih dari dataset validasi, termasuk contoh *out-of-catalog*. Perangkat identik tanpa SN/MAC/identitas jaringan tidak dapat dibedakan hanya dari foto dan lokasi.

## Pilihan model (benchmark, jangan hardcode satu model)

1. Baseline embedding dari pretrained image encoder ringan (mis. MobileNetV3 feature extractor atau model CLIP ringan) yang lisensi/weight-nya sesuai penggunaan perusahaan.
2. Ekstrak feature vector, L2-normalize, simpan embedding beserta `model_name`, `model_version`, preprocessing version.
3. Bandingkan model kandidat menggunakan dataset perangkat nyata. Pilih berdasarkan **top-1/top-3 accuracy, unknown rejection, latency, RAM, dan false-positive rate**.
4. Tidak perlu fine-tuning sebelum baseline terbukti tidak memadai. Jangan menganggap ImageNet classifier otomatis mengetahui SKU AP tertentu.
5. Minimal 5–15 foto referensi per model dari beberapa sudut dan 3–5 foto uji **terpisah**; jangan bocorkan gambar yang sama atau near-duplicate ke train/reference dan test.

## Data & skema

| Entitas | Kolom inti | Catatan |
|---|---|---|
| `image_embeddings` | id UUID, reference_image_id FK, encoder_name, encoder_version, preprocess_version, vector_data, created_at | simpan array/bytea/JSON sesuai skala; migrasi ke pgvector bila perlu |
| `recognition_jobs` | id UUID, created_by FK, status, image_key, requested_at, finished_at, error_code nullable, model_version | job bisa synchronous MVP dengan batas timeout, atau queue ringan jika perlu |
| `survey_observations` | id UUID, asset_id nullable FK, observed_location_id nullable FK, image_key, label_image_key nullable, observed_by, observed_at, review_status, result_status | **asset_id nullable** untuk UNKNOWN |
| `recognition_candidates` | id UUID, observation_id FK, device_model_id nullable FK, asset_id nullable FK, rank, similarity_score nullable, evidence_json, decision_reason | pisahkan model candidates dan asset candidates jika lebih jelas |
| `ocr_results` | id UUID, observation_id FK, raw_text, parsed_identifiers_json, engine_version, corrected_text nullable, reviewed_by nullable | jangan menghapus raw evidence |
| `recognition_reviews` | id UUID, observation_id FK, reviewer_id, decision, selected_model_id nullable, selected_asset_id nullable, notes, reviewed_at | keputusan review immutable/auditable |

Simpan original image dengan storage provider Sprint 1A; hindari penyimpanan base64 besar di database. Metadata harus mengandung source, timestamp, model version, serta alasan keputusan.

## Status keputusan

- `KNOWN_MODEL_CANDIDATE`: kandidat model dari katalog, belum identitas unit.
- `UNKNOWN_MODEL`: tak ada kandidat yang memenuhi threshold; bisa disimpan tanpa model/asset.
- `PROBABLE_ASSET`: kandidat unit didukung bukti namun belum cukup unik.
- `AMBIGUOUS`: ≥2 unit identik tidak bisa dibedakan.
- `CONFLICT`: SN/MAC atau lokasi/histori saling bertentangan.
- `VERIFIED_ASSET`: hanya setelah identifier kuat yang cocok dan/atau verifikasi manusia sesuai kebijakan yang terdokumentasi; **tidak boleh hanya model + lokasi**.

## Evidence rules minimum

| Bukti | Penggunaan | Larangan |
|---|---|---|
| SN cocok | kandidat identitas kuat setelah normalisasi + konteks manufacturer | jangan percaya OCR mentah tanpa pemeriksaan kualitas |
| MAC cocok | kandidat identitas kuat jika jenis MAC dan sumber jelas | jangan samakan BSSID dengan MAC perangkat tanpa mapping |
| Model visual | filter/ranking model | tidak membuktikan unit fisik |
| Lokasi resmi | menaikkan prioritas kandidat | bukan bukti tunggal untuk verified |
| Movement history | menjelaskan lokasi yang diharapkan dan perubahan | histori bisa terlambat diperbarui |
| Observasi terbaru | mendeteksi konflik/ketidaksesuaian | tidak otomatis update master |

**Contoh kasus:** 8 AP Ruijie AP680-L, AP-001 SN 123456789 di Lounge dan AP-002 SN 2158763 di Lobby (data ilustratif). Foto AP680-L di Lounge dengan SN rusak → AP-001 `PROBABLE_ASSET`, **bukan VERIFIED**. Foto AP680-L di Villa 10 dengan SN milik AP-003 dan lokasi master Villa 1 → `CONFLICT` + review/movement workflow Sprint 2. Dua AP identik satu lokasi tanpa identifier → `AMBIGUOUS`.

## API minimum

| Method | Route | Fungsi |
|---|---|---|
| POST | `/recognition/model-candidates` | upload foto, top-k model, UNKNOWN support |
| POST | `/recognition/ocr` | upload foto label, raw/parsed text |
| POST | `/recognition/observations` | simpan bukti foto, lokasi, OCR, kandidat |
| GET | `/recognition/observations/{id}` | detail bukti, versi model, kandidat |
| POST | `/recognition/observations/{id}/review` | review human: match/unknown/conflict |
| GET | `/recognition/metrics` | evaluasi internal ADMIN saja |

**Security:** hanya authenticated, rate limit sederhana, MIME/magic-byte/dimensions validation, batas file dan timeout, hindari path traversal, privacy-safe logging; request data pihak ketiga **tidak dilakukan otomatis**.

## UI minimum

- Upload/capture **satu foto** terlebih dahulu (bukan live recognition).
- Hasil top-3 kandidat model + skor similarity yang diberi label "similarity", bukan confidence.
- Input foto label opsional, OCR + koreksi manual.
- Pemilihan lokasi dari master Sprint 2, bukan GPS saja.
- Kandidat Asset ID dengan penjelasan bukti dan conflict warning.
- Tombol `Tidak dikenali` / `Perangkat baru` → observation UNKNOWN.
- Review Admin: approve kandidat, mark unknown, minta foto tambahan; tidak mengubah lokasi tanpa movement approval.

## Task Codex berurutan

1. **3-01 Evaluation harness:** dataset manifest, split referensi/test/unknown, metrics, latency benchmark CPU, laporan baseline; pilih encoder setelah bukti benchmark.
2. **3-02 Embedding index:** adapter encoder, index/reference rebuild, top-k search, threshold unknown, versioning, tests.
3. **3-03 OCR:** PaddleOCR CPU adapter, normalisasi SN/MAC, fallback manual, tests label rusak/buram.
4. **3-04 Evidence fusion:** deterministic rules, model-vs-unit separation, statuses, explanations, conflict tests.
5. **3-05 Observation/review API + UI:** upload, candidates, human review, audit, RBAC, tests.
6. **3-06 End-to-end evaluation:** 8 AP identical, unknown model, location conflict, false positive review, resource profiling, docs.

## Acceptance criteria

- [ ] Pengenalan foto baru mengembalikan top-3 model kandidat dan model/version/score.
- [ ] Foto unknown tidak dipaksa menjadi model katalog.
- [ ] Perangkat belum terdaftar bisa dibuat sebagai observation dengan `asset_id=null`.
- [ ] OCR raw output, parsed identifiers, dan koreksi manusia disimpan terpisah.
- [ ] AP680-L dengan SN rusak di Lounge menghasilkan kandidat AP-001 **PROBABLE**, bukan VERIFIED.
- [ ] Dua AP identik tanpa identifier kuat menghasilkan AMBIGUOUS.
- [ ] SN cocok tetapi lokasi bertentangan menghasilkan CONFLICT dan **tidak otomatis mutasi**.
- [ ] Hasil review punya actor/time/evidence dan tidak menghapus prediksi awal.
- [ ] Tidak ada dependensi Ollama atau API cloud wajib.
- [ ] Profil CPU/RAM/latency tercatat pada laptop target atau lingkungan yang jelas spesifikasinya.
- [ ] Evaluation report memuat top-1/top-3, unknown precision/recall, false positive, latency p50/p95, ukuran dataset dan batasan.
- [ ] Target awal **top-3 ≥90%** pada foto uji terpisah dijadikan *go/no-go metric*, bukan klaim sebelum benchmark. Threshold unknown dipilih berdasarkan hasil nyata.
- [ ] RBAC, upload security, migration, API/UI tests lulus.

## Fallback dan roadmap

Jika embedding belum akurat: tampilkan kategori umum + OCR logo/model + top-k dengan label ketidakpastian; minta foto tambahan atau manual review. Cloud vision opsional **setelah** review privasi, biaya, retensi data, dan opt-in per request. Integrasi controller Ruijie, real-time video, offline sync lengkap, dan training custom detector masuk sprint lanjutan, bukan Sprint 3.

## Kontrak kerja dengan Codex

1. Baca `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/BUSINESS_RULES.md`, dan migration yang sudah ada sebelum mengubah kode. **Repository adalah sumber kebenaran implementasi**; dokumen ini adalah spesifikasi target, bukan klaim fitur sudah tersedia.
2. Inspeksi struktur, dependensi, API, autentikasi/RBAC, pola testing, dan keadaan Git; rangkum gap terhadap sprint.
3. Buat rencana implementasi singkat, lalu kerjakan **satu task terbatasi per iterasi**. Jangan mengerjakan sprint berikutnya.
4. Pertahankan backward compatibility bila memungkinkan; setiap perubahan skema wajib migration Alembic yang reversible bila aman. Jangan mengedit migration yang sudah diterapkan.
5. Gunakan validasi Pydantic, SQLAlchemy, dependency RBAC server-side, transaksi database, dan test positif/negatif. Jangan menaruh secret, foto aset asli, atau database dump di Git.
6. Setelah task selesai, laporkan file yang berubah, perintah yang benar-benar dijalankan, hasil test nyata, risiko, dan langkah manual yang tersisa. Jangan mengklaim test lulus bila tidak dijalankan.
7. Jika detail implementasi Sprint 0 berbeda dari asumsi dokumen, **adaptasikan ke pola yang sudah ada**, jelaskan trade-off, dan jangan membangun sistem paralel.

## Perintah validasi umum (sesuaikan dengan repository)

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose exec api alembic upgrade head
docker compose exec api pytest -q
# Jika frontend container memuat tooling development:
docker compose exec web npm run lint
docker compose exec web npx tsc --noEmit
```

> Jika image runtime tidak menyertakan pytest/npm development tooling, gunakan mekanisme test lokal atau service test yang sudah disediakan repository. Pastikan hasilnya dicatat.

## Prompt pembuka untuk chat baru / Codex

```text
Implementasikan AssetVision IT Sprint 3 berdasarkan docs/sprints/SPRINT_3_RECOGNITION_ENGINE.md. Baca AGENTS.md, katalog model, registry unit, lokasi/movement, dan migration existing. Kerjakan task 3-01 saja: siapkan evaluation harness, format dataset manifest, benchmark dua kandidat embedding ringan di CPU, metrik top-1/top-3/unknown/latency, dan laporan. Jangan langsung membuat UI atau mengunci model sebelum benchmark. Jangan menggunakan Ollama atau API berbayar. Laporkan hasil test nyata dan tunggu approval untuk 3-02.
```
