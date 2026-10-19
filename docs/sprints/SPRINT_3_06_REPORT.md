# Task 3-06 — Evaluasi end-to-end recognition

Evaluasi skenario aplikasi, runner HTTP/profil dan dokumentasi diimplementasikan. Pemilihan
encoder/threshold dan accuracy perangkat nyata tetap NO_GO karena dataset independen beberapa
model + unknown belum tersedia. Tidak memulai task/sprint berikutnya. Tidak commit atau push.

## Review Task 3-05 dan scope

Awal working tree bersih, HEAD `24df242` (Task3-05), main lima commit di depan origin/main. Review laporan,
diff/arsitektur observation/review, kontrak, migration0011, private uploads, auth/proxy dan
suite existing dilakukan sebelum editing. Task3-05 menyimpan original prediction immutable,
review terpisah, raw OCR/manual terpisah, dan tidak memutasi master. Batas ini dipertahankan.
Graph MCP hanya mengindeks payload-cms-villa, sehingga source lokal dipakai untuk discovery.

Task ini hanya menambah tes/harness evaluasi dan docs; tidak mengubah source API/UI/fusion,
schema, dependency, environment atau threshold produksi. Tidak ada migration/seed/rebuild
index development, foto nyata baru di Git, atau auto-create aset dari recognition. Fixture
8unit sintetis dibuat hanya dalam database test terisolasi dan temporary private storage.

## Implementasi

- test_recognition_e2e.py: sembilan skenario dengan empat model sintetis dan delapan AP identik.
  Index/search benar-benar dijalankan dengan encoder sintetis; acceptance visual disuntikkan
  sesudah search hanya pada cabang test, diberi reason eksplisit, tanpa calibration palsu.
  OCR sintetis salah dengan score0.99 menguji human correction/review, bukan akurasi OCR.
- Skenario: damaged SN di Lounge→PROBABLE/null; empat identik satu lokasi→AMBIGUOUS;
  delapan tanpa lokasi→AMBIGUOUS8; explicit UNKNOWN; SN/lokasi conflict ditolak409 saat review;
  salah pilih unit409; checked unique match; rawOCR false positive vs correction; index
  uncalibrated→UNCERTAIN/UNKNOWN. Semua memeriksa audit/actor/time/prediction/master tetap.
- smoke_recognition_evaluation.py: HTTP nyata Next SSR/proxy/FastAPI/PostGIS, delapan registry
  AP created/placed lewat API, empat observasi/review, dua false MATCH409, preview ACL,
  VIEWER read/review403, accuracy null. Default empty-index/manual fallback, tanpa mock server.
- evaluate-recognition.sh + recognition_evaluation_profile.py + compose.recognition-eval.yaml:
  repeatable test stack, batas CPU/RAM, cgroup-v2 lifetime peak dan CPU delta, latency per
  operasi; report baru eksklusif tanpa overwrite, hanya agregat bebas payload privat.
- RECOGNITION_END_TO_END.md mendokumentasikan boundary/scope/metrik/gate dan cara rerun.
  SPRINT_3_06_BASELINE.json menyimpan agregat HTTP dan profil dua encoder, tanpa foto/path/
  prediction per-image. README/TESTING/Sprint3 menghubungkan protokol dan status yang terbatas.

## Pengujian dan hasil

Pemeriksaan awal tes baru gagal karena representasi timestamp SQLite: response create
menyimpan timezoneUTC, pembacaan ulang SQLite menghilangkan offset. Assertion membandingkan
snapshot GET yang sama dan tetap memeriksa actor/time; PostgreSQL wajib offset-aware.
Tidak mengubah source produk untuk perbedaan testDB tersebut. Ruff awal menemukan style
pada berkas baru, diformat/diperbaiki. Targeted berikutnya9passed; assertion penolakan rawOCR
false-match ditambahkan sebelum build regression final. Run awal tidak dianggap bukti final.

Hasil regression final dicatat setelah proses selesai pada bagian penutupan laporan ini.
Tidak menganggap test yang masih berjalan sudah lulus.

Perintah yang dijalankan (Ubuntu WSL2):

```bash
# Targeted iterasi dan regression final:
docker compose --profile test run --rm --no-deps --volume "$PWD/apps/api:/app:ro" api-test python -m pytest -q tests/test_recognition_e2e.py --tb=short --show-capture=no
bash infra/check.sh --postgres
bash infra/evaluate-recognition.sh /tmp/av-sprint3-06-http-v1.json
bash infra/benchmark-recognition.sh data/samples/grandstream-wp810 data/recognition-eval/wp810-sprint3-06-v1 data/recognition-eval/wp810-profile-v1/manifest.json
bash -n infra/evaluate-recognition.sh
python3 -m py_compile infra/recognition_evaluation_profile.py
git diff --check
```

Ruff format/check berkas API dan collector host dijalankan pada image api-test dengan repo
ter-mount ke/repo, user0 khusus tooling; tidak mengubah runtime UID. Compose override config
--quiet lulus. Percobaan runner terhadap report existing menghasilkan exit2 sebelum setup,
isi file tetap identik. Fingerprint/hash dibaca lewat Python/subprocess tanpa mencetak secrets.
Log utama /tmp/av-sprint3-06-full.log, /tmp/av-sprint3-06-http-v1.log dan
/tmp/av-sprint3-06-cpu-profile.log. Targeted iterasi /tmp/av-sprint3-06-targeted2.log.


## Evaluasi HTTP dan resource aktual

`bash infra/evaluate-recognition.sh /tmp/av-sprint3-06-http-v1.json` exit0. Keempat skenario
unknown/location_conflict/false_positive/checked_match lulus. Semua delapan response master
dan location/history sebelum/sesudah identik, original evidence setiap observasi identik.
Prediksi unchecked pada konflik masih PROBABLE; saat checked MATCH dilakukan ditolak409,
kemudian ADMIN menyimpan CONFLICT tanpa perubahan lokasi. Ini sesuai batas trust3-05.

| Operasi HTTP | N | p50 ms | p95 ms | Max ms |
|---|---:|---:|---:|---:|
| Upload device/OCR | 2 | 28.41 | 35.45 | 36.23 |
| Create observation | 4 | 53.31 | 102.07 | 109.69 |
| Review (termasuk409) | 6 | 23.02 | 25.93 | 26.07 |
| Read terukur | 3 | 12.25 | 33.34 | 35.68 |

| Layanan test | Peak cgroup MiB | Limit MiB | CPU workload s |
|---|---:|---:|---:|
| API (2CPU) | 144.50 | 768 | 3.158 |
| Web (1CPU) | 66.27 | 512 | 1.940 |
| PostgreSQL/PostGIS | 244.20 | 768 | 0.622 |

Satu sesi dingin serial, tanpa warmup, PNG32x24; bukan latency foto smartphone/model inference
atau SLA. Setup/login/CSRF tidak termasuk latency tabel; CPU delta termasuk setup/login dan
health traffic. Peak lifetime termasuk startup/pagecache, bukan processRSS. Runner test/host
RAM tidak dihitung. Ada web throttling0.259s selama workload, tercatat dalam JSON. Tidak
menyimpulkan kapasitas concurrency atau combined CPU-adapter environment dari profil ini.
HTTP stack otomatis stopped lewat trap, terpisah dari API/web/db development.

## Profil CPU sample pengguna

Perintah aktual:
`bash infra/benchmark-recognition.sh data/samples/grandstream-wp810 data/recognition-eval/wp810-sprint3-06-v1 data/recognition-eval/wp810-profile-v1/manifest.json`
Exit0, dua proses/networknone/read-only, CPU2/memory2GiB, Python3.12.15, torch2.10.0+cpu,
torchvision0.25.0+cpu, NumPy2.2.4, Ryzen5600H WSL2. Pinned weights/preprocess hash tercatat
pada aggregateJSON. Enam foto nyata, warmup5, repeat3 (18sample timed), reference_count0.

| Encoder | Cold load ms | Decode+encode p50/p95 ms | Encoder p50/p95 ms | Peak process RSS MiB |
|---|---:|---:|---:|---:|
| MobileNetV3 Small | 101.74 | 24.60 / 27.77 | 6.91 / 8.69 | 341.54 |
| ShuffleNetV2 0.5x | 68.57 | 36.89 / 50.40 | 9.93 / 15.13 | 337.30 |

Tidak ada search reference, upload/network/DB dalam latency ini. Angka berbeda scope dari
HTTP/cgroup tabel sebelumnya. Tidak mengevaluasi accuracy, threshold, unknown precision/
recall atau false acceptance nyata; semua metrics/threshold null, selection_eligible false,
NO_GO dan encoder_selection DEFERRED_INCOMPLETE_REAL_DATASET. Tidak memakai foto WP810
sebagai referensi/index aplikasi, mengubah source sample atau mengarang split independen.
Tidak mengklaim benchmark OCR label nyata/environment gabungan torch+paddle/manual browserUAT.

## Data existing dan gate

Fingerprint read-only /tmp/av-sprint3-06-before.json diambil sebelum editing, mencakup seluruh
tabel/kolom/timestamp/version/PostGIS/storage;12sampleSHA dan identitas container DB disimpan.
Pengujian writer memakai db-test/assetvision_test tmpfs, bukan development. Fingerprint final
dan bukti checks dicatat pada penutupan. Tidak ada schema baru atau perubahan data yang
seharusnya diabaikan. .env/credentials/foto/weights/dump privat tidak ditambahkan ke Git.

Pengguna mengarahkan pemeriksaan seluruh data/samples. Inventaris aktual 15 foto: AP680-L: 3,
WP810: 6, Lenovo IdeaPad Slim 3: 5, unknown: 1. Seluruhnya lolos decoded bounds285..1600side,
byte hash unik dan tidak ada dHash-near-duplicate pairs menurut guard. Tidak ada manifest
evaluation/reference/calibration/test atau capture-group independen yang diberikan. Minimum
harness≥4model dan tiapmodel≥5reference+2calibration+3test; unknown≥3calibration+3test belum
terpenuhi. Jumlah foto bukan bukti independensi unit/sesi; tidak membagi foto sembarang untuk
mengarang accuracy. Manifest profile-only baru disimpan di data/recognition-eval (ignored),
model label dari folder; unknown diberi token unclassified-profile-only khusus profil, bukan
klaim model katalog. Timestamp capture null, tidak memakai mtime. BaselineSHA30berkas (15foto
+15sidecar) diambil sebelum analisis folder tambahan. Agregat audit tersimpan di baselineJSON.
Acceptance accuracy Sprint3 tetap unchecked. Skenario sintetis membuktikan policy/perilaku
aplikasi, bukan top3≥90% perangkat nyata. Belum dapat menyatakan semua acceptance Sprint3
terpenuhi atau memilih encoder produksi. Gate berikutnya membutuhkan dataset berizin >=4
model dengan reference/calibration/test dan unknown independen sesuai protokol3-01.
Task/sprint berikutnya tidak dimulai; commit/push hanya atas permintaan terpisah.


## Profil seluruh sample yang dikonfirmasi pengguna

Setelah suite PostgreSQL selesai/stopped, benchmark profile-only diulang serial untuk semua
15 foto dalam data/samples. Manifest baru tidak mengubah foto/sidecar; tidak mengarang capture
time atau split evaluasi. Foto AP680-L yang berjumlah tiga juga belum membuktikan delapan
unit fisik independen. Perintah aktual:

```bash
bash infra/benchmark-recognition.sh data/samples data/recognition-eval/local-samples-sprint3-06-run-v1 data/recognition-eval/local-samples-sprint3-06-profile-v1/manifest.json
```

Exit0; tiap encoder memakai15foto ×3repeat =45 timed sample, warmup5, CPU2/mem2GiB,
networknone/read-only dataset. Lingkungan/pinned weights sama dengan profil WP810 di atas.

| Encoder | Cold load ms | Decode+encode p50/p95 ms | Encoder p50/p95 ms | Peak process RSS MiB |
|---|---:|---:|---:|---:|
| MobileNetV3 Small | 101.94 | 24.99 / 30.00 | 6.77 / 7.60 | 346.40 |
| ShuffleNetV2 0.5x | 53.93 | 33.17 / 41.12 | 8.34 / 9.43 | 339.70 |

Agregat baselineJSON sekarang mencakup inventory audit dan kedua profil (WP8106 dan seluruh
15foto). Source foto tidak menjadi referensi aplikasi. Metrics/threshold tetap null,
NO_GO/DEFERRED, tanpa top1/top3/unknown precision/recall palsu. Log tambahan:
/tmp/av-sprint3-06-all-cpu-profile.log; audit /tmp/av-sprint3-06-samples-audit.json.

## Penutupan: hasil final dan preservasi

`bash infra/check.sh --postgres` selesai **exit0** pada source final:

| Pemeriksaan aktual | Hasil |
|---|---|
| Backend SQLite | 837 passed, 35 skipped, 226.08detik |
| Backend PostgreSQL/PostGIS | 861 passed, 11 skipped, 356.39detik |
| Frontend ESLint/TypeScript/tests | 88 passed, 0 failed |
| API Ruff / pip check | All checks passed / No broken requirements |
| HTTP E2E/profil resource | 4skenario lulus, report exit0 |
| CPU profile WP810 | 2encoder ×18timed samples, exit0 |
| CPU profile seluruh sample | 2encoder ×45timed samples, exit0 |
| Shell/collector syntax, Compose config, diff/whitespace | lulus |

Sembilan tes baru termasuk dalam kedua suite final. SQLite melewati24tes khusus PostgreSQL
dan11tes optional CPU; PostgreSQL melewati11tes CPU karena library opsional tidak ditambahkan
ke image default. Profil encoder nyata tetap dijalankan terpisah sebagaimana tabel, bukan
menyamarkan skip menjadi pass. Ada satu warning Starlette/httpx deprecation pada backend;
tidak mengganti dependency dalam task evaluasi ini. Migrasi/login/unauthorized/RBAC/history/
concurrency existing tercakup dalam suite final, tanpa migration baru. Tidak mengulang suite
setelah hanya menambahkan hasil pada docs.

121hash source API (119 pendahulu +2 modul test baru) cocok dengan image api-test dan tetap
cocok sesudah regression; manifest /tmp/av-sprint3-06-api-source.json. 81hash source frontend
tetap identik dengan pendahulu dan frontend check image. Source app/migrations/UI production
tidak berubah. Log yang masih berjalan tidak dihitung; exit0 penuh sudah dikonfirmasi.

Fingerprint /tmp/av-sprint3-06-after.json **identik byte** dengan before.json dan midpoint:
seluruh tabel/kolom/timestamp/version/PostGIS/storage existing utuh, termasuk head0011 dan
tiga tabel recognition yang tetap kosong. Tidak mengecualikan tabel audit/auth atau storage.
Dua belas hash sample WP810 dan30hash seluruh sample/sidecar sama dengan baseline masing-
masing. Container DB tetap sama; development API/web/db tetap healthy dan tidak di-restart.
HTTP read-only health200/ready200/anonymous observations401. Test db-test dan kedua layanan
smoke sudah stopped. Tidak seed/login/rebuild/kalibrasi ke development.

Berkas berubah (3 existing +8 baru):

- README.md
- docs/TESTING.md
- docs/sprints/SPRINT_3_RECOGNITION_ENGINE.md
- apps/api/tests/test_recognition_e2e.py
- apps/api/tests/smoke_recognition_evaluation.py
- compose.recognition-eval.yaml
- infra/evaluate-recognition.sh
- infra/recognition_evaluation_profile.py
- docs/RECOGNITION_END_TO_END.md
- docs/sprints/SPRINT_3_06_BASELINE.json
- docs/sprints/SPRINT_3_06_REPORT.md

Staging kosong; HEAD tetap24df242/main ahead5. Tidak commit/push dan tidak memulai task atau
sprint berikutnya. Evaluasi alur/profil task ini selesai, tetapi acceptance akurasi nyata
Sprint3 tetap belum terpenuhi sampai dataset independen dilengkapi.


## Review akhir dan commit lokal — 20 Oktober 2026

Diff akhir seluruh 11 berkas ditinjau sebelum commit. Tidak ditemukan temuan penghalang.
Dokumentasi diperjelas agar ringkasan profil mencakup seluruh15foto dan membedakan status
FAILED subprocess tes dari timeout/error collector yang dapat meninggalkan report tidak
lengkap. Tidak ada perubahan source tes/runner/API/UI selama review ini.

121hash API dan81hash frontend dicocokkan ulang dengan source pengujian final, semuanya
identik. Log hasil837SQLite/861PostgreSQL/88frontend, HTTP empat skenario dan profil dua
encoder pada6/15foto dikonfirmasi kembali; aggregateJSON cocok dengan raw reports. Ini
pemeriksaan bukti final, bukan klaim menjalankan ulang seluruh suite pada tahap commit.

Fingerprint read-only /tmp/av-sprint3-06-commit-review.json identik byte dengan baseline
before.json dan final.json: seluruh data/storage existing tetap utuh. Semua30hash foto/
sidecar (termasuk12WP810) dan identitas container DB tetap sama. Tidak ada foto/weights/
secrets/dump private dalam11berkas commit. Diff/whitespace bersih dan staging dipilih
eksplisit sesuai daftar berkas di atas.

Pesan commit lokal: test: add Sprint 3-06 end-to-end recognition evaluation. Pernyataan
belum commit pada bagian implementasi sebelumnya mencatat kondisi saat itu. Tidak push
ke origin/main atau memulai task/sprint berikutnya. Acceptance akurasi nyata tetap NO_GO.
