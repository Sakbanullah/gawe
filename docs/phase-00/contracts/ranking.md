# Aturan Ranking — Draft Phase 0

**Status:** draft Phase 0. Belum disetujui.
**Source of Truth terkait:** [`../../source-of-truth/PRODUCT.md`](../../source-of-truth/PRODUCT.md) §5.1–5.3, [`../../source-of-truth/DECISIONS.md`](../../source-of-truth/DECISIONS.md) (K10, K11, K23, D13–D16), [`../../domains/ELIGIBILITY-AND-SCORING.md`](../../domains/ELIGIBILITY-AND-SCORING.md) §5.
**Target implementasi:** `backend/src/gawe/ranking/` pada Phase 3–4.

Dokumen ini mengunci aturan urutan. Formula fit ada di [`../../domains/ELIGIBILITY-AND-SCORING.md`](../../domains/ELIGIBILITY-AND-SCORING.md) §4.1 dan tidak diubah di sini.

---

## 1. Tiga Nilai yang Tidak Boleh Dicampur

| Nilai | Peran dalam ranking |
|---|---|
| `eligibility_status` | Penentu apakah lowongan masuk daftar utama |
| `fit_score` | Kunci urutan utama |
| `priority_tier` | Tie-breaker di dalam band, bukan kunci utama |

Aturan keras:

- `fit_score` tidak memuat `eligibility_status` atau `priority_tier`.
- Ranking utama hanya `eligible`.
- `needs_review` dan `ineligible` tidak masuk daftar utama dan tidak membawa `fit_score`.
- Mengubah tier tidak mengubah `fit_score`.

---

## 2. Input

Satu `ranking_run` menerima:

| Field | Wajib | Catatan |
|---|---|---|
| `profile_version_id` | ya | Profil yang dipakai |
| `candidates[]` | ya | Satu item per job |
| `candidates[].job_id` | ya | Kunci stabil terakhir |
| `candidates[].eligibility_status` | ya | `eligible`, `needs_review`, `ineligible` |
| `candidates[].fit_score` | hanya `eligible` | Integer 0–100; `null` untuk status lain |
| `candidates[].priority_tier` | ya | `P1`–`P4` atau `unclassified` |
| `candidates[].posted_at` | tidak | ISO 8601; `null` bila tidak diketahui |
| `tie_window` | ya | Default 0; maksimum 20 |

Input tidak valid (misalnya `fit_score` ada untuk `needs_review`) ditolak, bukan diperbaiki diam-diam.

---

## 3. Algoritma

```text
rank(candidates, tie_window):
  eligible = [c for c in candidates if c.eligibility_status == "eligible"]
  eligible.sort(by = (-fit_score, job_id))          # urutan dasar stabil

  result = []
  i = 0
  while i < len(eligible):
      band_top = eligible[i].fit_score
      band = []
      while i < len(eligible) and band_top - eligible[i].fit_score <= tie_window:
          band.append(eligible[i])
          i += 1
      band.sort(by = (
          tier_rank(priority_tier),                  # P1 < P2 < P3 < P4 < unclassified
          -posted_at,                                # terbaru dulu; null terakhir
          job_id,                                    # stabil
      ))
      result.extend(band)

  return result
```

`tier_rank`: `P1`=1, `P2`=2, `P3`=3, `P4`=4, `unclassified`=5.

Aturan band:

- `tie_window = 0` berarti hanya skor identik yang satu band.
- Band ditentukan dari skor tertinggi band, bukan dari selisih antar-tetangga. Ini mencegah rantai band yang melebar tanpa batas.
- Tier hanya berlaku di dalam band. P1 dengan fit rendah tidak boleh mengalahkan P2 dengan fit tinggi di luar band.
- `posted_at` yang tidak diketahui diletakkan setelah yang diketahui, di dalam band yang sama.
- `job_id` adalah kunci terakhir agar urutan deterministik dan pagination stabil.

---

## 4. Output

```json
{
  "ranking_run_id": "rnk_...",
  "profile_version_id": "prf_...",
  "tie_window": 0,
  "primary": "fit_score_desc",
  "tie_breaker": ["priority_tier", "posted_at_desc", "job_id"],
  "computed_at": "...",
  "sections": {
    "eligible": [
      {
        "rank": 1,
        "job_id": "job_...",
        "fit_score": 88,
        "priority_tier": "P2",
        "posted_at": "...",
        "band_id": 1
      }
    ],
    "needs_review": [
      {
        "job_id": "job_...",
        "reason_summary": "...",
        "fit_score": null
      }
    ],
    "ineligible": [
      {
        "job_id": "job_...",
        "reason_summary": "...",
        "fit_score": null
      }
    ]
  },
  "counts": {
    "eligible": 1,
    "needs_review": 1,
    "ineligible": 1
  }
}
```

Aturan output:

- `sections.needs_review` dan `sections.ineligible` tidak diurutkan dengan `fit_score`.
- `band_id` ditampilkan agar pengguna melihat mengapa dua skor berbeda bertukar posisi saat `tie_window > 0`.
- `primary` selalu `fit_score_desc` pada ranking tersimpan. Sort tampilan lain tidak mengubah output ini.

---

## 5. Sort Tampilan

| Sort | Sifat |
|---|---|
| `ranking` (default) | Memakai `ranking_run` tersimpan |
| `fit_score_desc` | Tampilan; tidak mengubah ranking tersimpan |
| `posted_at_desc` | Tampilan; diberi label |
| `priority_tier` | Tampilan; bukan default; diberi label |

Filter (`eligibility`, `tier`, `market`, `work_mode`, `min_fit_score`) tidak mengubah skor, eligibility, atau ranking tersimpan.

---

## 6. Fixture dan Test Invariant

Fixture: [`../fixtures/ranking/ranking_cases.json`](../fixtures/ranking/ranking_cases.json).

Test yang wajib ada saat implementasi:

| # | Invariant |
|---|---|
| 1 | Daftar utama hanya `eligible` |
| 2 | `needs_review`/`ineligible` tidak membawa `fit_score` |
| 3 | Skor identik diurutkan tier lalu `posted_at` lalu `job_id` |
| 4 | `tie_window = 0` tidak menukar skor berbeda |
| 5 | `tie_window = 5` menukar skor berbeda dalam band sesuai tier |
| 6 | P1 fit rendah tidak mengalahkan P2 fit tinggi di luar band |
| 7 | `unclassified` berada setelah P1–P4 di dalam band |
| 8 | Mengubah tier tidak mengubah `fit_score` |
| 9 | Urutan deterministik untuk input yang diacak |
| 10 | `posted_at` null berada setelah yang diketahui |

Test invariant nomor 1–7 dan 9 dijalankan oleh `tools/check-phase-00.py` terhadap fixture, sebagai bukti aturan dapat dieksekusi. Test aplikasi sebenarnya dibuat di Phase 3–4.

---

## 7. Yang Tetap `OPEN`

| Item | Status |
|---|---|
| Ambang rekomendasi (`apply_now`, `consider`, `stretch`) | `OPEN` — Phase 3/4 |
| Kalibrasi bobot dan ambang fit | `OPEN` |
| Apakah `experience_fit` default 0.5 selalu tepat | `OPEN` |
| Virtualisasi tabel untuk data besar | `OPEN` — Phase 4 |
| D21 override `ineligible` | `OPEN` — tidak memengaruhi ranking |
