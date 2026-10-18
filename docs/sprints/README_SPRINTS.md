# AssetVision IT — Sprint Execution Pack

Paket spesifikasi **mandiri** untuk digunakan pada chat terpisah dan Codex. Urutan wajib:

1. `SPRINT_1A_DEVICE_CATALOG.md` — master model & foto referensi.
2. `SPRINT_1B_ASSET_REGISTRY.md` — unit fisik & identifier.
3. `SPRINT_2_LOCATION_MOVEMENT.md` — lokasi, mutasi, approval, histori.
4. `SPRINT_3_RECOGNITION_ENGINE.md` — embedding ringan, OCR, unknown, evidence fusion.

## Lokasi file di repository

Salin ke `docs/sprints/`. Jangan menganggap file ini menggantikan `AGENTS.md` atau source code. Codex harus selalu membaca kode/migration aktual.

```bash
mkdir -p docs/sprints
# salin file SPRINT_*.md ke docs/sprints/
git add docs/sprints
git commit -m "docs: add implementation specs for sprints 1A-3"
```

## Workflow hemat token

- Buka **chat baru untuk setiap sprint**; sertakan satu dokumen sprint, bukan semua riwayat diskusi.
- Dalam Codex, cukup arahkan ke `docs/sprints/<nama-file>.md` dan `AGENTS.md`; jangan tempel ulang dokumen panjang jika sudah ada di repository.
- Minta **satu task ID** per eksekusi (contoh `1A-01`), review dan test, baru task berikutnya.
- Pada chat baru, berikan ringkasan singkat: sprint selesai terakhir, branch/commit saat ini, error atau gap, dan task yang ingin dikerjakan.
- Jangan memasukkan `.env`, kredensial, foto aset asli, atau dump database ke chat/Git.

## Template pembuka chat baru

```text
Project: AssetVision IT.
Sprint sebelumnya: [selesai / commit].
Sprint aktif: [1A / 1B / 2 / 3].
Dokumen spesifikasi: docs/sprints/[filename].
Task aktif: [mis. 1A-01].
Status repository: [ringkas].
Tolong bantu review implementasi, urutan perintah, hasil test, dan prompt Codex untuk task ini saja. Ikuti AGENTS.md dan jangan mengerjakan task lain.
```

**Penting:** angka waktu dan target akurasi dalam dokumen adalah estimasi/acceptance target, bukan hasil uji aktual.
