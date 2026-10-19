# Task 3-05 — Observation/review API dan UI

Task 3-05 menghubungkan upload foto privat, kandidat model/OCR, koreksi manual, observasi,
fusion dan review ADMIN yang diaudit. Prediksi awal dan review tersimpan terpisah. Tidak ada
perubahan master unit/identifier/lokasi dari recognition. Task 3-06 tidak dimulai.

## Review pendahulu dan keputusan arsitektur

Awal pada main/HEAD d0b61cb, empat commit lokal di atas origin/main, working tree bersih.
Hasil Task 3-04 ditinjau: fungsi fusion murni, complete snapshot tepercaya, model vs unit,
status konservatif dan requires_review, tanpa auto-VERIFIED. Core fusion/normalizer tersebut
tidak diedit. AGENTS, Sprint3, README/arsitektur/aturan bisnis, auth/storage/migrations/tests
existing ditinjau. Graph MCP hanya mempunyai payload-cms-villa, sehingga discovery fallback
source lokal digunakan. Tidak memakai data nyata/foto perangkat existing sebagai fixture tes.

Implementasi tetap modular monolith. Tiga tabel baru immutable menyimpan completed job,
observasi/prediksi awal dan satu review terminal. JSON evidence memisahkan visual, raw OCR,
parsed/manual correction, fusion dan context snapshot. Asset_id hasil hanya berasal dari
review.selected_asset_id nullable; bukan overwrite/link langsung pada prediksi awal.

Default menjaga NO_GO visual3-01 dan manual fallback. Adapter CPU opsional di belakang
interfaces3-02/3-03, process deadlines dan explicit environment; tidak memilih encoder atau
threshold produksi. Tidak mengubah dependency/lock default API/web, tidak menambah Redis,
queue, microservice, controller, cloud wajib atau auto-create model/asset.

## Implementasi dan policy

- OFFICER/ADMIN upload/catat observasi. VIEWER baca. ADMIN saja review/metrics.
- Capture original bounded privat, SHA source; preview JPEG max1600side tanpa EXIF/GPS.
  Metadata raw tidak disajikan sebagai static file; filename/path browser diabaikan.
- Durable cleanup reservation sebelum put, key UUID exclusive. Cleanup existing kini juga
  melindungi recognition job yang mereferensikan key pada ambiguous commit.
- JSON64KiB, foto max8MiB/4096side/16Mpixel/singleframe/MIME+magic. Rate10attemptwrites/menit/
  akun tersimpan durable, termasuk malformed requests. Semaphore satu analysis dan dua preview
  per worker, busy429. Max20pendingMODEL+20OCR/akun, dapat dipulihkan di UI tanpa upload ulang.
- Request UUID/digest menangani retry observasi actor/payload sama. Key reuse lain409.
  Concurrent review hanya satu pemenang; trigger melarang UPDATE/DELETE seluruh evidence/review.
- Snapshot master bounded lengkap, latest non-dismissed location observation dan approved
  placement/movement, catalog fingerprint/index generation. PG SERIALIZABLE + hierarchy/asset
  locks; serialization/deadlock/stale409 tanpa retry diam-diam. Master version tidak dinaikkan.
- MATCH mensyaratkan explicit label_checked, indices manual correction retained, SN scoped
  manufacturer atau typed LAN/WLAN MAC, unique VERIFIED master claim, unit/version/context sama
  dan fusion ulang tanpa conflict/ambiguity. Model+lokasi/raw OCR/manual entry saja tidak cukup.
- VERIFIED_ASSET hanya ada pada review manusia sesuai unique-checked-identifier-v1, bukan
  output fusion awal. UNKNOWN/CONFLICT/MORE_PHOTOS tetap unlinked. Audit atomik dengan keputusan.
- UI /recognition memakai auth shell/context/proxy/CSRF existing. Similarity diberi label
  similarity; model/version dan unit terpisah, raw OCR/koreksi/prediksi awal/review tetap terlihat.
  Draft dijaga dan submit diblokir setelah gagal/tidak pasti, termasuk malformed200 response.
  Riwayat/pending evidence mendukung recovery, tidak ada automatic retry.

Kontrak/policy lengkap: ../RECOGNITION_OBSERVATIONS.md. OpenAPI request schemas ditambahkan.

## Berkas berubah

- .env.example
- README.md
- apps/api/app/config.py
- apps/api/app/image_service.py
- apps/api/app/main.py
- apps/api/app/models.py
- apps/api/app/openapi.py
- apps/api/app/recognition_http_encoder.py
- apps/api/app/recognition_http_worker.py
- apps/api/app/recognition_observations.py
- apps/api/app/recognition_routes.py
- apps/api/app/recognition_uploads.py
- apps/api/app/routes.py
- apps/api/app/survey_schemas.py
- apps/api/app/survey_service.py
- apps/api/app/survey_snapshot.py
- apps/api/migrations/versions/0011_recognition_surveys.py
- apps/api/tests/smoke_recognition.py
- apps/api/tests/test_asset_csv.py
- apps/api/tests/test_health.py
- apps/api/tests/test_migrations.py
- apps/api/tests/test_ocr_cpu.py
- apps/api/tests/test_recognition_cpu.py
- apps/api/tests/test_surveys.py
- apps/web/app/assets/layout.tsx
- apps/web/app/catalog/layout.tsx
- apps/web/app/dashboard/page.tsx
- apps/web/app/recognition/error.tsx
- apps/web/app/recognition/layout.tsx
- apps/web/app/recognition/loading.tsx
- apps/web/app/recognition/page.tsx
- apps/web/app/recognition/recognition.css
- apps/web/components/recognition/recognition-workspace.tsx
- apps/web/components/recognition/survey-detail.tsx
- apps/web/lib/proxy.ts
- apps/web/lib/recognition.ts
- apps/web/tests/proxy.test.ts
- apps/web/tests/recognition-ui.test.tsx
- compose.recognition-api.yaml
- docs/API_CONTRACT.md
- docs/ARCHITECTURE.md
- docs/BUSINESS_RULES.md
- docs/DATABASE.md
- docs/RECOGNITION_OBSERVATIONS.md
- docs/TESTING.md
- docs/sprints/SPRINT_3_05_REPORT.md
- docs/sprints/SPRINT_3_RECOGNITION_ENGINE.md
- infra/recognition-api/Dockerfile
- infra/recognition-api/Dockerfile.dockerignore
- infra/smoke-recognition.sh

## Pengujian aktual dan iterasi

Pengujian awal menemukan fixture model belum mengisi environment, bukan bug domain; fixture
diperbaiki. Login VIEWER fixture memakai domain .invalid yang ditolak validator email; diganti
example.com, tanpa melemahkan auth. Frontend awal gagal lint karena setState langsung dalam
effect dan komentar rule ESLint yang tidak tersedia; diperbaiki mengikuti pola project.
Ruff mendeteksi formatting/unused assignment pada berkas baru; diperbaiki tanpa skip rule.

Targeted awal28passed, kemudian64passed/1PGskip. Source final targeted survey/health/OpenAPI:
**71 passed,1 skipped**,21.74detik. Test mencakup ownership/RBAC/CSRF/MIME, private original vs
preview, raw/corrected, exact retry, stale/collision/location/unverified refusal, immutable
SQL guards, preserved predecessor migration, populated downgrade refusal, audit rollback,
process timeout fallback, pending recovery dan readiness/OpenAPI. Race PG dijalankan di suitePG.

Run full awal dihentikan setelah source berubah, tidak dihitung sebagai final. Run SQLite
berikutnya belum selesai ketika transport WSL sempat WSAETIMEDOUT; container test milik task
itu dihentikan lalu diulang. Development DB/API/web tidak dihentikan untuk mengatasi masalah.
Tidak merestart WSL/daemon atau mengubah resolver/secrets/.env. Angka run terputus bukan pass.

CPU awal6encoder/5OCRpassed. Percobaan ulang encoder bersamaan build/tests lain mendapat satu
EncoderUnavailable (5 passed/1failed); tidak mengklaim penyebab internal yang tidak terukur.
Source sama diulang serial setelah build: **6 passed,36.67detik**, OCR **5 passed,24.43detik**.
Deadlines tidak dilonggarkan untuk membuat tes lulus. Default adapter tetap unavailable/
UNCERTAIN/manual fallback bila dependency/weight/deadline tidak memenuhi, tanpa identitas palsu.

Hasil final yang sudah dikonfirmasi:

| Pemeriksaan | Hasil |
|---|---|
| SQLite | 828 passed,35 skipped;214.98detik;exit0 |
| PostgreSQL/PostGIS | 852 passed,11 skipped;656.92detik;exit0 |
| Frontend lint/TypeScript/jsdom+proxy | 88 passed,0 failed;exit0 |
| API Ruff/pipcheck | All checks passed / No broken requirements |
| Encoder CPU final | 6 passed;36.67detik |
| Paddle OCR CPU final, termasuk HTTP nyata | 5 passed;24.43detik |
| API test/runtime source proof | 119hash cocok (118Python+OCRmanifest) |
| Frontend test image source proof | 81hash cocok |
| Smoke HTTP/SSR/proxy/DB final | 5 kelompok PASS;exit0 |
| Compose CPU override / shell / diff check | lulus |

SQLite final dan smoke selesai dengan hasil tabel di atas. Runtime API/web berhasil dibangun
(dengan TypeScript production build) dan diperbarui setelah checks wajib selesai. PostgreSQL
writer selesai/stopped sebelum smoke memulai database test baru; SQLite memakai in-memory DB
terpisah. Tidak ada dua writer db-test bersamaan.

CPU tests memakai pinned local environments3-02/3-03, current source read-only, networknone,
CPU2/mem2GiB/tmpfs256MiB, tanpa volume DB/storage development. Semua11CPU tests dilewati di
API default lalu dijalankan aktual di image masing-masing. Ini pengujian correctness/plumbing,
bukan akurasi OCR/visual nyata, benchmark latency SLA atau evaluasi E2E Task3-06.

Perintah utama yang benar-benar dijalankan (Ubuntu WSL2):

```bash
# Run awal (dihentikan, bukan hasil final):
bash infra/check.sh --postgres
# Suite final melalui image test khusus, PostgreSQL writer selalu serial:
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose --profile test run --rm --no-deps web-check npm run check
bash infra/smoke-recognition.sh
docker compose build api web
docker compose -f compose.yaml -f compose.recognition-api.yaml config --quiet
bash -n infra/smoke-recognition.sh
git diff --check
```

CPU6+5 dijalankan dengan `docker run --network none --read-only --tmpfs /tmp:size=256m
--cpus 2 --memory 2g --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges`, mount
apps/api ke/app:ro, entrypointpython, masing-masing pytest test_recognition_cpu.py dan
test_ocr_cpu.py pada image optional. Ruff format/check melalui bind/src dengan user0 hanya
untuk tooling. Runtime tetap UID10001. Hash/log/fingerprint diverifikasi lewat Python/subprocess.

Log final: /tmp/av-sprint3-05-final-postgres.log, /tmp/av-sprint3-05-web-final2.log,
/tmp/av-sprint3-05-encoder-final.log, /tmp/av-sprint3-05-ocr-final.log,
/tmp/av-sprint3-05-sqlite-final.log dan /tmp/av-sprint3-05-smoke-verified.log.

## Preservasi dan batas

Baseline /tmp/av-sprint3-05-before.json diambil sebelum editing: seluruh tabel/kolom/timestamp/
version/PostGIS/storage. Midpoint identik byte;12hash foto/sidecar WP810 cocok baseline3-04,
identitas container DB sama. Tidak ada seed/rebuild/calibration/inference terhadap development.
Schema development tetap0010 selama testing dan baru naik0011 pada deployment tervalidasi. Migration0011 hanya
menambah tiga tabel kosong dan trigger/index, tidak mengubah kolom/master/history lama.

Tidak ada foto nyata, weights, secrets, dump DB atau artefak private baru di Git. .env existing
tidak diedit; hanya .env.example didokumentasikan. Optional CPU API compose dibuat opt-in,
tidak diaktifkan otomatis. Tidak mengklaim environment gabungan torch+paddle telah diuji.
Tidak ada manual browser UAT pada tahap ini; jsdom dan smoke HTTP/SSR merupakan bukti terpisah.
Hasil final deployment/preservasi tercatat pada penutupan di bawah.
Tidak commit/push dan tidak memulai Task3-06.


## Penutupan dan preservasi final

Smoke pertama gagal pada helper assertion cache SSR: helper API mengharuskan string tepat
no-store, sedangkan Next memakai header private/no-cache/no-store. Assertion diperbaiki menjadi
keberadaan no-store, bukan melemahkan cache aplikasi. Smoke diulang dan lulus lima kelompok;
kemudian UI diperbaiki untuk menampilkan path hierarki lokasi dan memilih foto lain dengan
koreksi label dikosongkan eksplisit. Frontend88tes dan production build diulang, lalu smoke
final pada build terbaru kembali lima kelompok PASS/exit0. Semua test/smoke services stopped.

119hash API final cocok dengan api-test dan runtime. Satu-satunya Python file yang berubah
setelah full regression adalah runner non-pytest tests/smoke_recognition.py (assertion SSR),
yang diuji ulang aktual melalui HTTP. Seluruh app/migration/test_ source tetap identik dengan
suite828/852. Manifest /tmp/av-sprint3-05-final-source.json; frontend81hash sesuai source88tes
pada image web-check, manifest /tmp/av-sprint3-05-final-web-source.json. Tidak mengklaim full
regression dijalankan ulang untuk perubahan runner smoke saja. Ruff/pipcheck image final lulus.

Sebelum deploy, /tmp/av-sprint3-05-pre-deploy.json identik byte dengan baseline before/midpoint.
Build migrate lalu `docker compose run --rm --no-deps migrate` menerapkan0011 saja; dilanjutkan
`docker compose up -d --no-deps --wait --wait-timeout 90 api web`. Kedua service healthy,
`alembic current`0011_recognition_surveys(head), `alembic check` No new upgrade operations.
Default API tidak memilih encoder/OCR, tidak merebuild index, tidak seed/login/infer ke data
existing. Container DB tidak direcreate/restart; API/web saja diperbarui untuk fitur task ini.

Fingerprint final /tmp/av-sprint3-05-after.json dibandingkan eksplisit dengan baseline:
**semua tabel/kolom/timestamp/version/PostGIS/storage lama identik**, kecuali satu revisi
alembic_version yang tepat0011. Tepat tiga tabel baru (recognition_jobs, survey_observations,
recognition_reviews), semuanya count0/hashes[]. Tidak mengabaikan perubahan data tabel lain.
Identitas container DB dan12hash foto/sidecar tetap sama. Verifikasi HTTP development read-only:
health200,ready200,recognition anonymous redirect ke/login200, APIobservations anonymous401.
Tidak menggunakan login/fixture di development, sehingga bukti keseluruhan data lama utuh.

Default UI tersedia di http://localhost:3000/recognition dengan login existing. Foto/model
baru tetap unknown/uncertain ketika belum ada eligible adapter/index/calibration; manual
label dan review sesuai policy tetap berfungsi. Tidak mengklaim accuracy nyata/GO atau manual
browser UAT; Task3-06 tidak dimulai. Semua50 berkas berada di working tree, staging kosong,
HEAD d0b61cb tetap main ahead4 origin/main; tidak membuat commit atau push.


Pemeriksaan penutupan terakhir: /tmp/av-sprint3-05-final.json identik byte dengan after.json
sesudah verifikasi HTTP.119hash API dan81hash web tetap cocok manifest final; newline/whitespace
semua berkas baru dan git diff --check lulus. Ruff pada image final kembali All checks passed.
HEAD/staging tetap unchanged/empty;50berkas (24tracked berubah,26baru), tanpa foto/weights/dump.


## Review akhir dan commit lokal — 20 Oktober 2026

Atas permintaan review/commit terpisah, diff akhir source, migration, upload/ACL, snapshot,
review policy, proxy, UI dan cakupan tes ditinjau. Tidak ditemukan temuan penghalang commit.
119 hash source API dan 81 hash frontend dicocokkan ulang dengan manifest final; seluruhnya
identik dengan source pengujian yang dilaporkan. Log final dikonfirmasi kembali: SQLite
828 passed/35 skipped, PostgreSQL852 passed/11 skipped, frontend88 passed, CPU encoder6 dan
OCR5 passed, serta smoke HTTP/SSR lima kelompok PASS. Ini pemeriksaan bukti final, bukan
klaim menjalankan ulang seluruh suite pada tahap commit. Tidak ada perubahan source produk
atau tes selama review akhir; hanya bagian laporan ini ditambahkan.

Fingerprint read-only /tmp/av-sprint3-05-commit-review.json identik byte dengan final.json:
seluruh data/storage existing dan tiga tabel baru kosong tetap sama. Dua belas hash sample
dan identitas container DB juga identik. Pemeriksaan whitespace/diff bersih. Tepat50 berkas
sesuai daftar di atas dipilih untuk commit lokal, tanpa foto, weights, secrets atau dump.
Pesan commit: feat: implement Sprint 3-05 recognition observations and review UI.
Pernyataan belum commit pada bagian implementasi sebelumnya mencatat kondisi saat itu.
Tidak push ke origin/main dan tidak memulai Task3-06; batas NO_GO/evaluasi nyata tetap berlaku.
