# Evidence fusion — Task 3-04

`app.evidence_fusion.fuse_evidence(FusionInput)` adalah fungsi internal murni tanpa DB,
filesystem, network, inference, atau perubahan master. Hasil JSON Pydantic dapat dipakai
oleh integrasi berikutnya. Tidak ada HTTP route/CLI/UI baru pada task ini.

## Input dan batas kepercayaan

Caller tepercaya harus menyediakan snapshot konsisten seluruh unit dan klaim aktif,
termasuk unit archived dan collision lintas model/produsen, bukan hasil pagination atau
filter visual. `complete_snapshot=true` adalah deklarasi caller, bukan bukti otomatis
kelengkapan DB. Maksimum500 unit,128 klaim per unit dan128 identifier; kelebihan ditolak,
tidak dipotong diam-diam. Soft-deleted claims wajib dikeluarkan caller. Metadata source,
verification, manufacturer, version dan lokasi berasal dari master, bukan formulir browser.
Tidak mengikat DTO ini langsung ke request HTTP; RBAC, query snapshot dan audit persisten
merupakan pekerjaan integrasi Task3-05, belum diimplementasikan di sini.

Input terpisah: SearchResult3-02 (model candidates/version/score), IdentifierCandidate3-03
(raw/normalized/source/issues), unit snapshots, lokasi/waktu pengamatan, latest non-dismissed
observation dan latest approved placement/movement. Pending/rejected/cancelled movement tidak
menjadi approved history. Caller memakai urutan latest/staleness Sprint2 existing.
Semua timestamp berzona; observed_at<=snapshot_at, evidence<=snapshot_at; UUID unit duplikat
atau field tambahan ditolak. Snapshot harus dibaca ulang sebelum keputusan persisten.

`human_checked=false` default, termasuk manual entry: mengetik koreksi bukan persetujuan.
Caller hanya boleh mengaktifkan flag sesudah manusia memeriksa label/sumber dan menyelesaikan
isu kualitas kandidat. Skor OCR0.85, skor cosine, kesamaan lokasi atau klaim master VERIFIED
sendiri tidak mengaktifkan flag. Pemeriksaan label ini berbeda dari keputusan final identitas.
Raw OCR, koreksi dan seluruh metadata engine tetap disimpan/dibawa caller secara terpisah;
fusion tidak mengedit atau menyalin ulang raw text menjadi master.

## Aturan v1

1. Model dan unit terpisah. Model_status dan model_candidates tetap terpisah dari candidates
   yang berisi asset UUID/version/model UUID/rank/reasons. Tidak ada confidence/probabilitas.
2. Visual hanya dipakai jika calibrated dan KNOWN_MODEL_CANDIDATE dari search tepercaya3-02.
   UNCERTAIN/UNKNOWN/uncalibrated tidak memilih unit. NO_GO encoder produksi3-01 tetap berlaku.
3. Model-only suggestions mengambil unit model aktif di lokasi yang sesuai jika ada;
   selain itu seluruh unit aktif dari model kandidat. Satu unit → PROBABLE_ASSET, beberapa
   → AMBIGUOUS. Penyempitan lokasi hanya saran dan tidak membuktikan keunikan fisik.
4. SN exact/case-sensitive memakai normalizer existing dan manufacturer UUID eksplisit
   untuk pemeriksaan kuat. Tanpa manufacturer, kecocokan hanya lemah. MAC LAN/WLAN exact
   type dan normalisasi existing; generic MAC/BSSID/MODEL tidak diperlakukan sebagai identitas
   unit. Tidak ada BSSID mapping otomatis, fuzzy repair, O/0 substitution atau placeholder.
   Zero/broadcast/multicast MAC ditolak sebagai bukti perangkat.
5. Raw OCR/unchecked manual hanya menjadi kandidat lemah. Kandidat diperiksa manusia dengan
   manufacturer/type yang cukup dibandingkan terhadap semua klaim aktif. Status master
   UNVERIFIED/DISPUTED ditandai dan tidak pernah menghasilkan verifikasi otomatis.
6. Semua collision dipertahankan termasuk unit archived. Identifier diperiksa yang mengarah
   ke unit berbeda, atau satu cocok dan satu tidak ditemukan → CONFLICT. Semua checked
   identifier tidak ditemukan → UNKNOWN tanpa fallback unit dari visual/lokasi. Collision tetap
   AMBIGUOUS walau identifier tambahan menyempitkan intersection; kebijakan konservatif
   meminta pemeriksaan collision. Tidak ada merge klaim/unit otomatis.
7. Identifier yang cocok tidak dibuang oleh filter model/lokasi. Model terkalibrasi bertentangan
   dengan model unit → CONFLICT. Lokasi resmi berbeda pada identifier diperiksa → CONFLICT,
   kecuali pengamatan lebih tua daripada verifikasi lokasi resmi (ditandai sebagai historis).
8. Latest observation/history sebelum verifikasi resmi atau sesudah pengamatan target diberi
   STALE_OR_LATER. Mismatch terhadap master pada bukti yang relevan ditandai; untuk kandidat
   identifier diperiksa menghasilkan CONFLICT. Histori tidak menjadi bukti tunggal identitas.
9. Prioritas status: CONFLICT > AMBIGUOUS > PROBABLE_ASSET > UNKNOWN. Unknown mendukung tanpa
   kandidat unit; UNKNOWN_MODEL dapat tetap memiliki kandidat unit dari identifier terpisah.
10. Semua hasil `requires_review=true`, policy_version=evidence-fusion-v1. **VERIFIED_ASSET
    sengaja tidak dikeluarkan v1**, bahkan dengan identifier unik. Kebijakan final mensyaratkan
    keputusan manusia eksplisit melalui review auditable Task3-05; task ini tidak membuatnya.

Reason codes stabil dan diurutkan; rank kandidat deterministik (identifier diperiksa, lokasi
resmi yang sama, UUID). Urutan snapshot unit tidak memengaruhi hasil. Tidak ada random/time-now.
Evidence berbeda tetap terlihat; tidak ada lokasi/version/identifier/master/observasi yang ditulis.

## Pengujian

`tests/test_evidence_fusion.py` memakai snapshot dan label sintetis, termasuk contoh Lounge,
dua unit identik, SN/location conflict, collision archived, manufacturer/case/MAC type,
OCR/manual default unchecked, NO_GO visual, histori stale, input bounds dan determinisme.
Ini uji aturan, bukan evaluasi akurasi OCR/visual perangkat nyata atau E2E delapan AP Task3-06.
Jalankan `bash infra/check.sh --postgres` untuk regresi lengkap pada DB uji terisolasi.
