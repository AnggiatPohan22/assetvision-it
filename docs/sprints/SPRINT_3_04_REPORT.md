# Task 3-04 — Evidence fusion

**Selesai pada scope internal engine; belum commit/push. Task3-05 tidak dimulai.**

| Pemeriksaan source final | Hasil aktual |
|---|---|
| Tes fusion terarah | 37passed,0.11detik |
| SQLite | 785passed,31skipped,237.52detik |
| PostgreSQL/PostGIS | 808passed,8skipped,326.08detik |
| Frontend lint/TypeScript/tests | lulus;78passed,0failed |
| API pipcheck/Ruff | lulus |
| Source108hash vs image final | identik |
| Fingerprint DB/storage existing | identik byte sebelum/sesudah |


## Scope dan review pendahulu

Task3-03 pada commit9cc5d68 ditinjau sebelum implementasi: OCRResult mempertahankan raw evidence,
manual correction terpisah, parser tidak memperbaiki karakter ambigu, MAC type dibedakan dan
seluruh hasil requires_review. Tidak ada perubahan terhadap source3-03 atau encoder/index3-02.
Working tree awal bersih pada main, tiga commit lokal di atas origin/main; tidak push.

AGENTS.md, README, ARCHITECTURE, BUSINESS_RULES, Sprint3, laporan3-03, schema/service OCR,
SearchResult, asset/identifier/location/observation dan migration0010 ditinjau. Graph MCP hanya
mendaftarkan payload-cms-villa sehingga source lokal dipakai sebagai fallback project ini.
Task3-04 diotorisasi eksplisit; scope Sprint0 historis pada AGENTS tidak membatalkan instruksi itu.

Implementasi dibatasi pada deterministic evidence fusion internal dan pengujiannya. Tidak ada
schema/migration, query/writer DB, auth flow, endpoint, UI, observasi/review persisten, inference
baru, seed, kalibrasi, rebuild index atau deployment. Task3-05 dan3-06 tidak dimulai.

## Hasil implementasi

- fusion_schemas.py: input/output Pydantic immutable/extra-forbid, bounded lengkap unit snapshot,
  active claims, metadata source/verification/manufacturer/version, waktu berzona, model/OCR DTO
  existing, lokasi resmi dan latest observation/approved history.
- evidence_fusion.py: fungsi murni deterministik, status PROBABLE_ASSET/AMBIGUOUS/CONFLICT/UNKNOWN,
  model_status/model_candidates terpisah dari unit candidates, reasons/rank/snapshot/policyversion.
- Normalisasi identifier memakai modul existing tanpa perubahan. SN exact case dan konteks
  manufacturer, MAC exact tipe LAN/WLAN; generic MAC/BSSID/model bukan bukti identitas unit.
- Skor visual/OCR tidak menjadi confidence/approval. Visual uncalibrated/UNCERTAIN/UNKNOWN tidak
  memilih unit; gate NO_GO produksi3-01 tetap berlaku. Model+lokasi hanya saran PROBABLE atau
  AMBIGUOUS. Unknown tidak dipaksa menjadi unit.
- Human-checked label berbeda dari final identity review. Default false untuk OCR maupun manual.
  Master UNVERIFIED/DISPUTED ditandai; collision tetap terlihat termasuk unit archived. Model
  mismatch, checked identifiers disagree, checked match+unmatched, lokasi/histori relevan yang
  bertentangan menghasilkan CONFLICT. Backdated/stale/later evidence tidak memalsukan konflik kini.
- V1 sengaja tidak mengeluarkan VERIFIED_ASSET. Semua hasil requires_review; kebijakan final
  membutuhkan review manusia auditable pada task integrasi berikutnya, belum dibuat di sini.

Snapshot lengkap adalah kontrak caller tepercaya, bukan HTTP request. Flag complete_snapshot
bukan pembuktian otomatis kelengkapan DB. Caller berikutnya harus membaca semua unit/klaim aktif,
menangani soft-delete, latest approved movement/non-dismissed observation dan snapshot konsisten.
Maksimum500unit/128claims/128identifiers; kelebihan ditolak eksplisit, tidak dipotong. Tidak
menerima browser-supplied human_checked sebagai otorisasi atau menyimpan keputusan dengan versi
snapshot lama. Batas dan tabel aturan lengkap ada di ../EVIDENCE_FUSION.md.

## Berkas berubah

Baru:

- apps/api/app/fusion_schemas.py
- apps/api/app/evidence_fusion.py
- apps/api/tests/test_evidence_fusion.py
- docs/EVIDENCE_FUSION.md
- docs/sprints/SPRINT_3_04_REPORT.md

Diperbarui: README.md, docs/ARCHITECTURE.md, docs/BUSINESS_RULES.md, docs/TESTING.md,
docs/sprints/SPRINT_3_RECOGNITION_ENGINE.md. Tidak ada dependency/env/Compose/frontend baru.

## Pengujian

35tes terarah awal lulus, ditambah2tes regresi final (37total): contoh Lounge PROBABLE, identik AMBIGUOUS, location-only
UNKNOWN, visual gate, checked serial/location CONFLICT, identifier disagreement/unmatched,
archived collision, manufacturer, MAC type/non-device rejection, SN case/no fuzzy repair,
unchecked manual/OCR contract, immutable raw/manual integration3-03, model mismatch, staleness,
permutation stable, input timestamp/bounds/duplicate/extra-field dan unverified master.

Format awal lewat user default container gagal menulis bind mount (permission denied).
Diulang dengan --user0 hanya pada tooling format source, lalu berhasil; runtime tetap non-root.
Tes terarah35passed/0.13detik. Full runner membangun image dari source yang diformat; manifest
108hash (107Python + OCRweightsmanifest) cocok byte dengan isi image api-test. Tidak memakai
hasil tes pendahulu sebagai hasil source task ini.

Hasil SQLite iterasi sebelum perbaikan unmatched: **783passed,31skipped**,196.89detik. Ruff dan pipcheck lulus.
Frontend lint/TypeScript lulus, **78passed,0failed**. PostgreSQL iterasi awal kemudian lulus
**806passed,8skipped**,351.47detik; runner exit0. Angka ini historis sebelum perbaikan unmatched,
bukan hasil final source terbaru.
Sanity run docker network-none/read-only tanpa env aplikasi berhasil import dan memanggil
fusion kosong, menghasilkan UNKNOWN. Tidak memerlukan JWT_SECRET atau koneksi database.

Perintah aktual utama (Ubuntu WSL2):

```bash
# Tes terarah pada source aktual read-only:
docker compose --profile test run --rm --no-deps \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/app:ro \
  api-test python -m pytest -q tests/test_evidence_fusion.py
# Ruff check dan format tiga file baru melalui api-test, bind /src; format --user0.
bash infra/check.sh --postgres
# Setelah tambahan2tes/perbaikan, build dan runner default final:
bash infra/check.sh
# PG final sesudah PG iterasi awal selesai/stopped, terpisah dari SQLite in-memory:
docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm \
  api-test python -m pytest -q
# Trap menghentikan hanya db-test setelah run PG.
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py \
  > /tmp/av-sprint3-04-before.json
# Fingerprint midpoint/final dibandingkan byte dengan baseline; read-only.
git diff --check
```

Pembacaan Git/source/log dan pemeriksaan manifest hash image/foto menggunakan Python/subprocess.
DB test tetap db-test/assetvision_test terisolasi tmpfs; bukan DB development. Tidak menjalankan
ulang inference CPU opsional karena adapter/model/decoder tidak berubah; hasil CPU3-03 adalah
bukti historis pendahulu, bukan eksekusi Task3-04. Tidak ada manual browser UAT karena tanpa UI.
Tidak ada klaim accuracy visual/OCR atau evaluasi E2E3-06 dari fixture aturan sintetis.

Review kasus negatif berikutnya menemukan checked identifier yang tidak ditemukan masih
mengizinkan fallback saran unit model/lokasi. Perbaikan final memblokir fallback tersebut:
semua checked identifier tidak ditemukan → UNKNOWN (termasuk SN+MAC baru), sedangkan match
plus unmatched tetap CONFLICT. Dua tes regresi ditambah;37passed/0.11detik. Anotasi collection
service diperjelas dan assertion no-auto-verification dibuat eksplisit. Runner default final
(SQLite/lint/frontend) dibangun ulang pada source terbaru; PostgreSQL final dijalankan serial
setelah runner PG iterasi awal berakhir. Tidak ada dua writer db-test bersamaan. Log/hasil
iterasi awal tidak dipakai sebagai hasil final source yang telah diperbaiki.

## Preservasi dan batas

Baseline /tmp/av-sprint3-04-before.json diambil sebelum editing memakai fingerprint read-only
seluruh tabel/kolom/timestamp/version/PostGIS/storage. Midpoint identik byte. Schema development
0010_embedding_index (head), alembic check No new upgrade operations. Tidak menjalankan migration
karena tanpa perubahan schema. Container DB sama dengan baseline3-03;12hash foto/sidecar WP810
cocok baseline3-03 dan disalin sebagai baseline task ini. Semua foto/weights/data privat tetap
ignored; tidak ada dump/secret/foto ditambahkan ke Git.

Preservasi final dikonfirmasi pada penutupan di bawah. Perubahan tetap belum
commit; tidak push. Task3-05 tidak dimulai. Integrasi DB/API/UI/review audited masih perlu task
terotorisasi berikutnya; module ini belum diekspos sebagai fitur browser development.


## Hasil final source setelah perbaikan

Runner default final `bash infra/check.sh` exit0:

- SQLite **785passed,31skipped**,237.52detik.
- Ruff All checks passed; pipcheck No broken requirements.
- Frontend ESLint/TypeScript lulus, **78passed,0failed**.
- Log `/tmp/av-sprint3-04-final-default.log`.

Manifest final `/tmp/av-sprint3-04-final-source.json` memuat108hash (107Python+manifestOCR),
cocok dengan image api-test final. Seluruh105hash pendahulu3-03 masih sama; hanya tiga source
baru ditambahkan. Source final tidak diedit lagi setelah build final. PostgreSQL final dicatat
di bawah. Tidak mengambil angka PG806 iterasi awal sebagai hasil final.


## Penutupan final

PostgreSQL/PostGIS final **808passed,8skipped**,326.08detik, runner exit0; log
`/tmp/av-sprint3-04-final-postgres.log`. Trap menghentikan hanya db-test dan selesai exit0.
SQLite31skip terdiri23khususPG/race+8CPUopsional; PG8skip hanya CPUopsional. Tes mencakup
regresi backend unit/API, login/unauthorized/RBAC, migrasi upgrade/check/downgrade/upgrade
terisolasi, konflik/version/audit, serta OCR/index non-inference. Kedua suite mempunyai satu
StarletteDeprecationWarning dependency existing; tidak ada kegagalan. Tidak ada smoke/browser
UAT baru pada task tanpa endpoint/UI; tidak mengklaim suite itu dijalankan ulang.

Final fingerprint `/tmp/av-sprint3-04-final.json` identik byte dengan before.json, midpoint dan
after.json, termasuk semua tabel/kolom/timestamp/version/PostGIS/storage tanpa pengecualian.
Ke12hash sample/sidecar dan identitas container DB tetap cocok baseline. API/web/db healthy,
tanpa recreate/restart/deploy development. Alembic tetap0010; tidak ada migration/seed/write
master atau inference/rebuild/kalibrasi development. Manifest108hash final masih cocok source
pada penutupan;105source pendahulu tetap sama. Tidak ada data/foto/weights/secret masuk Git.

Review penutupan:10berkas (5tracked docs berubah,5baru), newline/whitespace berkas baru dan
`git diff --check` lulus. Staging kosong, HEAD9cc5d68/main tetap tiga commit lokal di atas
origin/main. Tidak membuat commit atau push dan tidak memulai Task3-05/3-06. Daftar berkas,
perintah, hasil aktual, iterasi perbaikan dan batas caller/synthetic sudah dicatat di atas.


## Review akhir dan commit lokal

Review final sepuluh berkas tidak menemukan temuan penghalang terhadap scope internal engine.
Source aplikasi/test tidak diubah pada review ini.108hash kembali cocok manifest final dan
image api-test teruji. Log final dikonfirmasi: SQLite785passed/31skipped, PG808passed/8skipped,
frontend78passed/0failed, Ruff/pipcheck lulus. Suite tidak diulang karena source identik dengan
versi yang telah diuji; konfirmasi log ini bukan eksekusi ulang pada review commit.

Fingerprint read-only terbaru `/tmp/av-sprint3-04-commit-review.json` identik byte dengan
baseline sebelum task;12hash sample/sidecar dan container DB tetap sama. Tidak ada perubahan
data existing, schema, runtime development atau aktivasi Task3-05. Kontrak caller tepercaya,
NO_GO visual, tanpa auto-verification dan batas fixture sintetis tetap didokumentasikan.

Staging dilakukan melalui10path eksplisit, disusul pemeriksaan staged diff/whitespace dan
commit lokal `feat: implement Sprint 3-04 deterministic evidence fusion`. Catatan belum commit
pada penutupan implementasi di atas adalah keadaan sebelum permintaan commit pengguna.
Tidak push dan tidak memulai Task3-05.
