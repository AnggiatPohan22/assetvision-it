# Laporan Task 3-03 — OCR label dan fallback manual

## Scope dan review pendahulu

Task 3-02 ditinjau dari commit eb6f7b9a2fa9bdcb165325f4010125bf29884f33, laporan, kontrak,
adapter, service index, decoder, migration dan hasil tes. Working tree awal bersih di main,
dua commit lokal di atas origin/main. Tidak ada push/commit baru dalam implementasi3-03.
Task 3-02 menyediakan index generasi immutable/CAS dan uncalibrated UNCERTAIN; gate NO_GO
encoder/threshold produksi tetap berlaku. Tidak ada perubahan index/model/threshold/master.

AGENTS.md, Sprint3 dan pola normalisasi identifier/storage/Compose/tests ditinjau sebelum
editing. Graph MCP list_projects hanya berisi payload-cms-villa sehingga fallback source lokal
digunakan untuk project ini. Memori dipakai untuk konvensi isolasi WSL/preservasi; status,
data dan hasil tes diperiksa kembali langsung. Pembatas Sprint0 pada AGENTS bukan larangan
menjalankan OCR pada task Sprint3 yang eksplisit diotorisasi pengguna.

Task 3-03 dibatasi pada Protocol OCREngine, adapter PaddleOCR CPU opsional, parser SN/MAC/model,
fallback manual, CLI transient dan pengujian. Tidak memulai Task 3-04/fusion atau3-05/API/UI/
observasi/review persisten. Tidak ada schema/migration, endpoint, frontend, env aplikasi,
auto-download runtime, cloud/GPU wajib, Tesseract wajib, atau perubahan master existing.

## Implementasi

- DTO frozen/extra-forbid membedakan raw_text/lines/ocr_candidates dan corrected_text/
  manual_candidates. Metadata berisi timestamp UTC, hash original image, engine/model/parser
  version. Semua kandidat requires_review; tidak mengeluarkan asset ID/VERIFIED atau probabilitas
  identitas. Nilai konflik tidak digabung diam-diam.
- Parser eksplisit berlabel SN/S/N/Serial, MAC/LAN/WLAN/Wi-Fi/BSSID/Model; mendukung label dan
  nilai pada dua line yang berdekatan. SN case/punctuation mengikuti master existing, placeholder
  ditolak. MAC canonical menggunakan normalizer existing. Generic MAC tidak menjadi LAN/WLAN,
  BSSID tetap BSSID. Zero/broadcast/multicast diberi issue, bukan bukti unik identitas perangkat.
- Tidak melakukan fuzzy label match, O/0/I/1 substitution, inferensi barcode/SN tanpa label,
  digit completion atau pembuatan identifier dari label rusak. Skor<0.85 hanya heuristik review,
  bukan threshold akurasi terkalibrasi. Raw evidence tidak berubah akibat koreksi manual.
- Decoder bounded Task 3-02 dipakai bersama; argumen byte limit eksplisit1KiB..8MiB memungkinkan
  CLI OCR tanpa JWT/DB settings, sedangkan pemanggil embedding tetap memakai konfigurasi existing.
  Batas OCR8MiB/4096side/16Mpixel/singleframe, MIME/magic dan EXIF RGB; foto tidak ditulis ulang.
- PaddleOCR3.2.0/PaddlePaddle3.2.0/PaddleX3.2.1 pada image Python3.12 terpisah, dua model mobile
  det/English rec PP-OCRv4 dengan enam checksum file. Preparation build eksplisit dari URL resmi,
  ekstraksi filename tetap; runtime menolak model missing/corrupt/symlink dan dependency mismatch.
  Orientation/unwarping off, BGR input, side max960, CPUthreads2, MKLDNNoff, tidak ada hub fallback.
- Child process per foto di-kill dan ditunggu ketika timeout30detik(default1..120). JSON bounded
  dan divalidasi parent, stdout/stderr engine tidak mencetak label/error. Container network none,
  read-only, tmpfs256MiB, CPU2/mem2GiB, tanpa DB/storage development/port/capabilities.
- Engine unavailable/timeout/invalid output/label tanpa kandidat mendukung MANUAL_REQUIRED;
  correction dapat diberikan tanpa engine atau bersama pembacaan OCR. Invalid image tetap ditolak,
  sekalipun operator memberi koreksi. CLI membaca file input bounded, pesan error generik exit2;
  fallback manual normal adalah hasil evidence exit0, bukan klaim OCR sukses.

## Berkas perubahan

- apps/api/app/ocr_schemas.py, ocr_parser.py, ocr_service.py, ocr_adapter.py, ocr_worker.py,
  ocr_cli.py, ocr_weights.json; recognition_encoder.py menambah batas byte eksplisit saja.
  identifier_values.py memisahkan enum/normalizer dari ORM; assets.py re-export kompatibel.
- apps/api/tests/test_ocr.py dan test_ocr_cpu.py.
- infra/ocr/Dockerfile, Dockerfile.dockerignore, requirements.txt/lock, prepare-models.py;
  prepare-system-packages.py untuk cache APT build; infra/check-ocr.sh dan compose.ocr.yaml.
- README, docs/OCR.md, ARCHITECTURE, API_CONTRACT, BUSINESS_RULES, TESTING,
  Sprint3 status dan laporan ini. Daftar final diperiksa melalui git status/diff.

## Pengujian dan iterasi

Tes awal parser/fallback66passed. Review berikutnya menemukan kebutuhan CLI tanpa konfigurasi
JWT/database; decoder diberi batas eksplisit tervalidasi dan ditambah tes tanpa Settings serta
penolakan bypass batas. Hasil terarah125passed/1PGskip (17.33detik) mencakup OCR+index3-02.
Kemudian invalid/oversized reading dipastikan mengarah ke fallback manual, bukan output parsial.

Regresi pertama gagal sebelum tes karena registry Docker IPv6/network unreachable. Retry build
berhasil dan regresi awal lulus SQLite741/31skip (201.12detik), PG764/8skip (325.13detik),
frontend78/0fail, Ruff/pipcheck. Itu bukan source final: tambahan tes/fallback setelahnya
mengharuskan runner final diulang. Tidak memakai hasil awal sebagai hasil final.

Build dependensi Paddle juga menemui kegagalan registry pertama, lalu unduhan wheel189MB
berjalan sangat lambat. Bootstrap download tersebut dihentikan dan cache wheel PyPI dibuat
melalui Windows, tiap file diverifikasi SHA256 dari metadata PyPI, tanpa mengubah .env/DNS
atau konfigurasi Docker global. Cache baru berada di ignored data/private/ocr-build-wheels,
bukan data pengguna atau Git. Build argument PIP_FIND_LINKS/PIP_NO_INDEX hanya mengatur
transport cache saat build, bukan konfigurasi inference/aplikasi. Hasil final dicatat di bawah.

Pemeriksaan CLI mandiri juga menemukan import normalizer dari assets.py menginisialisasi
konfigurasi DB melalui ORM. Enum IdentifierType, MAC_TYPES dan normalize_identifier dipisah
ke identifier_values.py; assets.py mempertahankan re-export. AST enum/fungsi dibandingkan
langsung dengan HEAD dan identik. CLI subprocess tanpa env JWT/DB kini73tes OCR lulus
(2.81detik). Full suite diulang setelah pemisahan ini; hasil sebelum pemisahan tidak dipakai
sebagai bukti source final.

Dependensi native OpenCV memerlukan libGL/glib pada image opsional. Karena transport paket
sistem juga lambat, helper build melakukan parallel bounded fetch setelah apt-get update,
memeriksa SHA256 dari metadata APT, lalu tetap menyerahkan verifikasi/install kepada APT.
Iterasi helper menangani print-uris tanpa field checksum dan direktori cache mount kosong;
perbaikan hanya menyentuh build, bukan service OCR/master. Cache APT berada pada BuildKit,
tidak pada image/runtime atau database. Semua kegagalan bootstrap tercatat sebagai gagal,
bukan hasil tes yang berhasil.

## Hasil final

| Pemeriksaan final | Hasil aktual |
|---|---|
| Full runner `bash infra/check.sh --postgres` | exit 0; log `/tmp/av-sprint3-03-verified-full.log` |
| SQLite | **748 passed, 31 skipped**, 222.34 detik |
| PostgreSQL/PostGIS | **771 passed, 8 skipped**, 377.46 detik |
| Frontend ESLint/TypeScript/tests | **lulus; 78 passed, 0 failed** |
| API pip check / Ruff | No broken requirements found / All checks passed |
| Paddle CPU final, pinned base + lock | **4 passed**, 16.74 detik; `/tmp/av-sprint3-03-verified-cpu-pinned.log` |
| Encoder CPU predecessor, current source | **4 passed**, 39.73 detik; `/tmp/av-sprint3-03-encoder-verified.log` |
| HTTP/SSR Sprint 0/1A/1B smoke | **20 kelompok PASS**, exit 0; `/tmp/av-sprint3-03-smoke.log` |
| Helper build Ruff / shell syntax / Compose / Git diff | lulus |

Skip SQLite: 23 khusus PG/race dan 8 opsional CPU (4 encoder + 4 OCR). Pada PG, hanya 8 CPU
tests yang dilewati; kedelapannya dijalankan pada image CPU masing-masing. Tidak ada manual
browser UAT/UI OCR baru karena task ini tidak menambahkan UI. Smoke mencakup login, anonymous,
RBAC, CSRF/version, katalog, foto/identifier/CSV/inventaris dan SSR dengan data test terisolasi.

CPU integration memakai dua public weights asli, font DejaVu generated 900x220, blur Gaussian,
checksum/symlink/missing rejection dan CLI aktual. Label bersih pada fixture ini menghasilkan
SN dan generic MAC yang diharapkan, tetap requires_review. Profile final satu label:
**7.726 detik**, child max RSS **620688 KiB (~606 MiB)**. Initial bootstrap sebelum lock juga
4 passed/21.51 detik; profile12.090 detik/619940 KiB. Angka tunggal ini bukan benchmark
held-out, warm-up/percentile SLA, akurasi perangkat nyata atau batas worst-case input.
Semua CPU tests network none/read-only/CPU2/mem2GiB/tmpfs; tidak memasang volume development.

Image final `assetvision-ocr:3-03`: `docker image inspect .Size` **2677675975 bytes (~2.49 GiB)**.
Footprint disk dependency cukup besar sehingga image tetap opt-in, bukan bagian API default.
RAM child fixture di bawah batas container2GiB; tidak mengklaim footprint semua foto/perangkat.
**106 package** pada requirements.lock cocok tepat dengan pip freeze image final. Base Python
3.12 dipin pada digest build yang berhasil, a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1.
Dua percobaan rebuild lock gagal sebelum tes karena token registry IPv6 unreachable; build
pinned berikutnya berhasil dan seluruh4CPU tests diulang. Source API104Python + manifest weights
cocok pada image api-test dan OCR final (105 hash), tanpa perubahan source setelah full suite.

Rebuild encoder normal sempat lambat mengunduh dependency API yang tidak berubah. Setelah
menghentikan build milik task tersebut, tes encoder aktual dijalankan memakai environment
image3-02 yang sudah terverifikasi, dengan source final `/app` dipasang read-only. Site-packages
berada di `/usr/local`, tidak tertutup mount; user evaluator tetap non-root. Empat CPU tests
lulus pada source terbaru, bukan mengambil hasil tes lama. SQLite file CLI tetap private/tmp.

Perintah utama aktual (Ubuntu WSL2, serial untuk semua writer db-test):

```bash
bash infra/check.sh --postgres
bash infra/smoke-sprint1b.sh
PIP_FIND_LINKS=http://127.0.0.1:8766 PIP_NO_INDEX=1 OCR_BUILD_NETWORK=host \
  OCR_MODEL_ARCHIVE_CACHE_URL=http://127.0.0.1:8766 bash infra/check-ocr.sh
# Cache loopback hanya berisi wheel PyPI terverifikasi dan dua archive weights publik;
# server sementara dihentikan setelah final build. Tidak menjadi dependency runtime.
docker run --rm --network none --read-only --tmpfs /tmp:size=256m \
  --cpus 2 --memory 2g --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges \
  -v /home/anggiatpohan/projects/assetvision-it/apps/api:/app:ro \
  --entrypoint python assetvision-recognition-index:3-02 \
  -m pytest -q tests/test_recognition_cpu.py
docker compose -f compose.yaml -f compose.ocr.yaml --profile ocr config --quiet
bash -n infra/check-ocr.sh
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python - < /tmp/av-20261019-2-05-fingerprint.py > /tmp/av-sprint3-03-after.json
git diff --check
git diff --cached --stat
```

Tes terarah dan Ruff format/check juga dijalankan lewat api-test dengan bind `/src` dan user0
untuk editing/permission source, bukan pada runtime API. Pemeriksaan AST enum/normalizer,
perbandingan105hash,106freeze dan fingerprint read-only menggunakan Python/subprocess;
cache unduhan memakai Windows Python3.13 karena DNS/transport WSL tidak stabil. Tidak mengubah
resolver, Docker daemon, credentials atau .env untuk mengatasi koneksi.


## Preservasi

Fingerprint read-only sebelum perubahan /tmp/av-sprint3-03-before.json merekam semua tabel,
kolom, timestamp/version, storage dan PostGIS. Baseline container DB dan12foto/sidecar WP810
juga dicatat. Tidak ada migrate/seed/login/rebuild/kalibrasi/identifier update atau penulisan
DB development dalam task ini. Pengujian DB menggunakan db-test/assetvision_test tmpfs saja;
CPU tests menggunakan label generated dalam container tanpa mount data development.

Sesudah full runner final dan20smoke PASS, /tmp/av-sprint3-03-after.json identik byte dengan
baseline before.json: seluruh tabel/kolom/timestamp/version/PostGIS/storage tanpa pengecualian.
Schema tetap0010_embedding_index; alembic current/check development mengonfirmasi head dan
No new upgrade operations. Tidak menjalankan migrate karena tidak ada perubahan schema.
Embedding generation/vector tetap kosong, head existing tidak berubah. Container DB tetap sama,
API/web/db healthy; development API/web tidak recreate/restart. Runtime default tetap predecessor
3-02; source final diuji pada api-test, runtime smoke dan image OCR opsional, tanpa deployment
fitur HTTP baru. Ke12hash foto/sidecar cocok baseline task ini dan baseline3-02.

Source final104Python+app/ocr_weights.json cocok byte/hash dengan image api-test. Manifest
/tmp/av-sprint3-03-verified-api-source.json; sembilan source harness3-01 dan weights/foto existing
tidak diedit. Tidak ada foto, weights atau dump nyata yang masuk staging/Git.

## Batas

Dataset label nyata held-out/ground truth belum ada. Synthetic clean/blurred label dan stub
menguji correctness kontrak/fallback dan integrasi, bukan akurasi umum perangkat nyata.
Tidak mengklaim OCR bisa membedakan delapan unit identik, membaca SN rusak, atau memverifikasi
asset. Heuristik score0.85 belum dikalibrasi. CPU child per foto menanggung cold-start;
container limits bukan SLA semua foto. Foto WP810 existing tetap privat dan tidak dijadikan
klaim benchmark OCR. Gate NO_GO visual3-01 tetap berlaku. Task berikutnya tidak dimulai.


## Penutupan

Task 3-03 selesai pada scope adapter/parser/manual CLI dan pengujiannya. Semua perubahan masih
unstaged; tidak membuat commit atau push. Task 3-04 dan task berikutnya tidak dimulai.
Penggunaan OCR nyata tetap memerlukan review label, bukan approval/identifier update otomatis.
Laporan ini dan OCR.md merinci berkas, perintah, hasil aktual, preservasi serta batas evaluasi.

Review penutupan memeriksa **28 berkas** (8 tracked berubah,20 baru), newline/whitespace,
ketiadaan foto/weights/dump/database pada daftar Git dan index staging kosong. Fingerprint
penutupan `/tmp/av-sprint3-03-final.json` kembali identik byte dengan baseline sebelum task,
tanpa pengecualian tabel/kolom;105hash source masih cocok manifest teruji. Server cache
loopback sementara sudah dihentikan dan port8766 tidak lagi menerima koneksi. Cache publik
ignored tetap tersedia lokal untuk rebuild, tidak termasuk source commit.


## Review akhir dan commit lokal

Review diff akhir atas28berkas tidak menemukan temuan penghalang. Catatan unstaged/tidak commit
pada penutupan implementasi di atas adalah keadaan sebelum permintaan commit dari pengguna.
Source aplikasi/test tidak diubah pada review ini.105hash source kembali cocok dengan manifest
teruji dan isi image api-test serta OCR final;106package cocok tepat dengan requirements.lock.
AST IdentifierType/normalize_identifier tetap identik dengan pendahulu. Bukti log dikonfirmasi:
SQLite748passed/31skipped, PostgreSQL771passed/8skipped, frontend78passed/0failed, Paddle CPU4passed,
encoder CPU4passed, dan20kelompok smoke PASS. Suite tidak dijalankan ulang karena source identik
dengan versi teruji; tidak mengklaim hasil log lama sebagai eksekusi baru pada review ini.

Fingerprint read-only terbaru `/tmp/av-sprint3-03-commit-review.json` identik byte dengan baseline
sebelum implementasi. Ke12hash foto/sidecar dan identitas container DB tetap sama; API/web/db
healthy. Tidak ada migrasi, perubahan data existing atau aktivasi inference development.
Perintah review mencakup `git diff --check`, pembacaan diff/source/log, pemeriksaan hash image,
pip freeze, AST dan fingerprint melalui Python, serta `docker compose ps`.

Staging memakai28path eksplisit, dilanjutkan `git diff --cached --check`, pemeriksaan daftar
staged dan commit lokal `feat: implement Sprint 3-03 CPU OCR and manual fallback`.
Tidak push dan tidak memulai Task3-04. Batas evaluasi sintetis dan gate NO_GO visual tetap berlaku.
