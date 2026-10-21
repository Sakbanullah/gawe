# Phase 5 — Aggregator dan Operasi

**Status:** belum dimulai. Menunggu Phase 4 dan persetujuan eksplisit.
**Sumber:** `PLAN.md` §13 Phase 5.

---

## 1. Tujuan dan Scope

Memperluas sumber remote + operability:

- Arbeitnow, Remotive, Jobicy, Himalayas, RemoteOK;
- attribution;
- cache;
- backup/restore/purge;
- laporan biaya per provider;
- hardening ekspor dan metadata.

Di luar scope: Playwright, OCR, model lokal (Phase 6). Sumber Indonesia terverifikasi sudah ditangani Phase 4.

---

## 2. Prasyarat dan Dependensi

- Phase 4 selesai dan disetujui.
- ToS/attribution per sumber dipahami.
- D10 belum final; retensi tetap sementara.

---

## 3. Dokumen Wajib Dibaca

1. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md)
2. [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md)
3. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md)
4. [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md)
5. [`../domains/SYSTEM.md`](../domains/SYSTEM.md)
6. [`../domains/DATABASE.md`](../domains/DATABASE.md)
7. [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md)
8. [`../domains/TESTING.md`](../domains/TESTING.md)

---

## 4. File atau Modul yang Diharapkan Berubah

```text
backend/src/gawe/jobs/sources/{arbeitnow.py,remotive.py,jobicy.py,remoteok.py}
backend/src/gawe/jobs/fetch.py (cache + attribution)
backend/src/gawe/cli.py (backup, restore, purge)
backend/src/gawe/export/ (hardening metadata)
backend/src/gawe/llm/cost.py (laporan biaya)
backend/tests/ (backup/restore/purge, attribution)
```

Lokasi mengikuti proposal `PLAN.md` §12.

---

## 5. Persyaratan dan Batasan

- Attribution ditampilkan untuk Remotive, Jobicy, Himalayas, RemoteOK, dan Arbeitnow bila disyaratkan.
- Batas harian dipatuhi: Remotive ~4 req/hari dengan delay 24 jam; Jobicy maks 1 poll/jam dengan jendela 7 hari; Himalayas 60/menit dan 10k/hari.
- Cache 24 jam; jangan polling.
- Rate limit per sumber dipatuhi.
- Backup/restore memakai dump MySQL; validasi schema version.
- Purge menghapus workspace + row/file terkait.
- Laporan biaya per provider/model/role.
- Metadata ekspor lengkap (ID, hash, nama file, waktu, status).
- Retensi tetap sementara sampai D10.

---

## 6. Keamanan, Privasi, dan Error Handling

- Backup tanpa secret.
- Restore tidak menimpa data lebih baru tanpa konfirmasi.
- Purge dengan konfirmasi untuk `--all`.
- Log tanpa PII.
- Attribution tidak boleh dihapus dari UI.
- ToS violation → hentikan sumber.

---

## 7. Acceptance Criteria

Dari `PLAN.md` §13 Phase 5:

- attribution tampil;
- cache 24 jam;
- backup/restore berhasil;
- purge menghapus data terkait.

Acceptance criteria tidak diubah.

---

## 8. Cara Verifikasi dan Bukti

- Test backup/restore.
- Test purge (row + file).
- Cek output attribution.
- Test cache.
- Test laporan biaya.
- Laporkan perintah, output, dan batasan.

---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak |
|---|---|
| D10 | Retensi final |
| D11 | API berbayar; default tidak |
| D8 | Enkripsi backup opsional |
| D17 | Cakupan Indonesia lanjutan di luar sumber Phase 4 |

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti bila:

- ToS/attribution tidak jelas;
- sumber memerlukan API berbayar;
- backup/restore berisiko kehilangan data;
- purge tidak dapat menghapus data terkait secara konsisten;
- muncul kebutuhan mengubah kebijakan retensi.

---

## 11. Gate Persetujuan

- Tidak ada pelanggaran ToS yang diketahui.
- Persetujuan eksplisit pengguna sebelum Phase 6.

---

## 12. Referensi PLAN.md

- §4.2 sumber aggregator dan etika akses
- §9.6 Backup, restore, hapus
- §13 Phase 5
- §14 kriteria 6, 26
- §15.4 D8, D10, D11, D17
