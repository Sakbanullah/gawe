# Phase 4 — Perluasan Sumber dan Skala Discovery

**Status:** infrastruktur registry/penjadwalan/skala sudah diimplementasikan (2026-10-22); penambahan sumber Indonesia dan adapter baru belum dimulai. Butuh persetujuan eksplisit.
**Sumber:** `PLAN.md` §13 Phase 4, §14, §4.2.

---

## 1. Tujuan dan Scope

Perluas cakupan discovery tanpa mengubah aturan eligibility, fit, atau ranking yang sudah ada di Phase 3:

- sumber Indonesia terverifikasi (D17);
- registry lanjutan: prioritas sumber, jadwal, kuota, riwayat kesehatan;
- skalabilitas tabel/filter Job Matches untuk volume besar;
- laporan kesehatan sumber dan data basi.

Di luar scope: agregator remote/EU dan operasi backup (Phase 5), OCR (Phase 6), perubahan aturan ranking, perubahan aturan approval/ekspor. Sumber `browser` dengan sesi login pengguna masuk Phase 7, bukan Phase 4.

**Catatan 2026-10-27 (Revisi 10, D26).** Phase ini tetap soal API resmi per perusahaan dan cakupan Indonesia (D17). Pita `priority_order` yang dipakai scheduler: 10-29 API, 30-69 agregator non-API, 900+ manual/ekstensi. Pita adalah konvensi, bukan constraint database; tidak ada migrasi. Adapter agregator resmi (`aggregator_api`) bukan scope phase ini: syaratnya D27 dan pengerjaannya di Phase 5.

---

## 2. Prasyarat dan Dependensi

- Phase 3 selesai: registry, adapter, normalisasi, dedupe, eligibility, ranking, UI matches sudah berjalan.
- **D17** dibutuhkan untuk mengaktifkan sumber Indonesia.
- ToS dan syarat attribution per sumber harus disetujui sebelum adapter diaktifkan.
- D10 tetap sementara untuk retensi cache.

---

## 3. Dokumen Wajib Dibaca

1. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md)
2. [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md)
3. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md)
4. [`../source-of-truth/UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md)
5. [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md) §4
6. [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md)
7. [`../domains/DATABASE.md`](../domains/DATABASE.md)
8. [`../domains/BACKEND.md`](../domains/BACKEND.md)
9. [`../domains/FRONTEND.md`](../domains/FRONTEND.md)
10. [`../domains/TESTING.md`](../domains/TESTING.md)

---

## 4. File atau Modul yang Diharapkan Berubah

```text
backend/src/gawe/jobs/sources/{indonesia_*.py}          (belum)
backend/src/gawe/jobs/sources/registry.py               (prioritas, jadwal, kuota, kesehatan)
backend/src/gawe/jobs/sources/base.py                   (ParsedJobs.complete)
backend/src/gawe/jobs/fetch.py                          (Retry-After)
backend/src/gawe/jobs/health.py
backend/src/gawe/services/{discovery_service.py,scheduler.py}
backend/src/gawe/services/assessment_service.py         (paging SQL)
backend/src/gawe/api/routes/{sources.py,matches.py}
backend/src/gawe/db/migrations/0013_source_schedule.sql
frontend/src/components/SourceRegistry.tsx              (kesehatan, prioritas, kuota)
backend/src/gawe/jobs/sources/{lever,ashby,greenhouse}.py (kontrak tidak berubah)
backend/tests/{test_source_health.py,test_sources.py}
```

`SourceHealthPanel.tsx` tidak dibuat terpisah: kolom kesehatan masuk ke
`SourceRegistry.tsx` yang sudah menampilkan daftar sumber, dan endpoint
`GET /api/settings/sources/health` tersedia untuk konsumen lain.

Lokasi mengikuti proposal `PLAN.md` §12.

---

## 5. Persyaratan dan Batasan

- Aturan Phase 3 tidak berubah: eligibility sebelum fit, fit hanya eligible, ranking fit-first.
- Setiap sumber baru wajib punya dokumentasi akses resmi dan catatan ToS.
- Sumber agregator dengan attribution ditangani di Phase 5, bukan Phase 4.
- Batas laju per sumber dipatuhi.
- Sumber tanpa API resmi tidak di-scrape; tetap gunakan fallback URL manual.
- Dedupe harus tetap akurat saat volume bertambah.
- Sumber `restricted`/`broken` tidak diaktifkan.
- Perubahan daftar sumber tidak boleh mengubah skor tersimpan.

---

## 6. Keamanan, Privasi, dan Error Handling

- URL guard + validasi redirect; host adapter dibatasi allowlist.
- Tanpa bypass CAPTCHA/login/paywall; tanpa rotasi proxy.
- 403/429 → berhenti untuk sumber itu; laporkan; backoff.
- `robots.txt` dicek untuk fetch HTML.
- Konten job tidak tepercaya; sanitasi untuk UI.
- Log tanpa isi job lengkap/PII.
- Error per sumber + retry; jangan hapus hasil sukses.
- Data >7 hari → warning.

---

## 7. Acceptance Criteria

Dari `PLAN.md` §13 Phase 4, ditambah kriteria cakupan:

- minimal dua sumber tambahan berjalan;
- batas laju dan kuota harian dipatuhi;
- status kesehatan sumber dan waktu fetch terlihat;
- dedupe tetap akurat pada volume lebih besar;
- ranking tidak berubah setelah penambahan sumber;
- `fit_score` tidak berubah saat tier diubah;
- filter/sort tidak mengubah skor;
- tabel menangani data besar tanpa memblokir UI;
- hasil parsial tidak dihapus saat sumber lain gagal.

Status per kriteria setelah implementasi infrastruktur 2026-10-22:

| Kriteria | Status | Bukti |
|---|---|---|
| Kuota harian dipatuhi | selesai | `jobs/health.py:quota_exhausted`, skip `source_quota_exhausted`, `tests/test_source_health.py` |
| Backoff dan `Retry-After` | selesai | `health.retry_at`, `FetchError.retry_after_s`, test `test_retry_after_is_a_floor_for_the_next_slot` |
| Kesehatan sumber terlihat | selesai | `health_status`/`consecutive_failures`/`next_run_at` di `SourceRegistryEntry` + `GET /api/settings/sources/health` + kolom UI |
| Hasil parsial tidak menutup job | selesai | `ParsedJobs.complete`, `partial_snapshot`, `test_partial_snapshot_does_not_close_jobs` |
| Filter/sort matches di SQL | selesai | `AssessmentService.matches_page`/`count_matches`, `job_rank`, `posted_at_epoch` |
| Minimal dua sumber tambahan | belum | butuh adapter baru + fixture |
| Dedupe pada volume besar | belum | belum ada test volume |
| Tabel menangani data besar | belum | UI masih merender seluruh halaman; belum ada test performa |
| Cakupan Indonesia (D17) | tidak berlaku | fokus worldwide |

Kriteria "sumber Indonesia yang dipakai sudah diverifikasi (D17)" **tidak berlaku**.
Keputusan pengguna 2026-10-22 menetapkan fokus produk adalah pencarian kerja
worldwide; Indonesia adalah bonus. Phase 4 tidak menunggu D17.

Klaim cakupan Indonesia tetap tidak boleh dibuat sampai D17 tersedia dan sumber
Indonesia diuji.

---

## 8. Cara Verifikasi dan Bukti

- Contract test adapter baru dengan respons fixture tersimpan.
- Uji live terbatas hanya pada sumber yang disetujui.
- Test kuota dan backoff.
- Test dedupe pada volume lebih besar.
- Test invariant ranking (tier swap, filter/sort).
- Test performa tabel.
- Laporkan perintah, output, dan batasan.

---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak |
|---|---|
| D17 | Sumber Indonesia; memblokir klaim cakupan Indonesia |
| D11 | API berbayar; default tidak |
| D10 | Retensi cache job sementara |

Implementasi adapter boleh berjalan dengan fixture, tetapi klaim cakupan tidak.

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti bila:

- cakupan Indonesia akan diklaim tanpa D17;
- sumber Indonesia akan diaktifkan tanpa verifikasi;
- ToS/robots melarang akses;
- rate limit atau kuota tidak dapat dipatuhi;
- ditemukan kebutuhan API berbayar;
- ranking berubah akibat penambahan sumber;
- muncul kebutuhan mengubah aturan tier/ranking.

---

## 11. Gate Persetujuan

- Hasil relevan untuk preferensi pengguna.
- Persetujuan eksplisit pengguna sebelum Phase 5.
- Klaim cakupan Indonesia hanya setelah D17 tersedia dan sumber diverifikasi.

---

## 12. Referensi PLAN.md

- §4.2 `/scrape` (prasyarat, preferensi, registry, pipeline, dedupe, tier, etika)
- §9.2 entity `source_registry`, `job`, `job_posting_version`
- §13 Phase 4
- §14 kriteria 6 dan 12
- §15.4 D3, D10, D11, D17
