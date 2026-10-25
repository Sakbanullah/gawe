# ELIGIBILITY-AND-SCORING — Eligibility, Fit Score, dan Ranking

**Domain:** eligibility, evidence, fit scoring, tier sebagai atribut, ranking, tie-breaker.
**Source of Truth terkait:** [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md) §5.1–5.3, [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) (D13–D16, D21).
**Referensi master:** `PLAN.md` §4.2 Eligibility gate, Ranking, Fit score; §14 kriteria 7–9, 12–13.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Eligibility gate: `eligible`, `ineligible`, `needs_review`.
- Pemeriksaan per requirement dengan kutipan dan bukti profil.
- Fit score untuk lowongan `eligible`.
- Komponen skor, verdict, confidence, gap.
- Ranking fit-first dan tie-breaker.
- Rekomendasi turunan (`apply_now`, `consider`, `stretch`, `needs_review`, `ineligible`).

**Tidak bertanggung jawab:**

- Fetch dan normalisasi job (domain discovery).
- Klasifikasi tier (domain discovery).
- Pembuatan dokumen (domain generation).
- Menentukan status keputusan produk.

---

## 2. Pemisahan Tiga Nilai

| Nilai | Arti | Sumber |
|---|---|---|
| `eligibility_status` | Kelayakan terhadap persyaratan wajib | Eligibility gate |
| `fit_score` | Kecocokan kompetensi dan bukti terhadap requirement | Formula fit |
| `priority_tier` | Preferensi pasar/mode kerja pengguna | Klasifikasi discovery |

Aturan keras:

- Fit score **tidak** memuat eligibility atau priority tier.
- Eligibility **tidak** memakai priority tier.
- Ranking utama hanya `eligible`.
- Tier hanya tie-breaker.

---

## 3. Eligibility Gate

### 3.1 Status

| Status | Definisi | Perlakuan |
|---|---|---|
| `eligible` | Semua persyaratan wajib yang dapat diverifikasi terpenuhi | Masuk ranking utama; fit dihitung; boleh lanjut dokumen |
| `ineligible` | Ada persyaratan wajib yang jelas tidak terpenuhi | Tidak masuk ranking utama; ditampilkan terpisah dengan alasan dan kutipan; tidak ada dokumen via alur normal |
| `needs_review` | Informasi tidak cukup, ambigu, atau bertentangan | Ditampilkan terpisah; bukan eligible; fit belum dihitung; dokumen diblokir |

### 3.2 Persyaratan yang dievaluasi

D25 (25 Oktober 2026) mengganti daftar gate sebelumnya. **Hanya skill wajib yang dapat membuat lowongan `ineligible`.**

- **Skill wajib (`category: other`).** Blokir eligibility hanya bila tidak ada satu pun skill yang diminta lowongan tercantum di profil. Bila skill disebut lowongan tetapi profil belum menyebutnya secara khusus, hasilnya `unknown` (bukan `ineligible`), karena profil adalah teks bebas: "tidak tertulis" tidak sama dengan "tidak punya". Jika lowongan tidak menyebut skill yang dapat dibaca, hasilnya `unknown`.
- **Pengalaman.** Tidak pernah memblokir. Kekurangan tahun pengalaman dicatat sebagai `unknown` beserta angkanya; pengguna memutuskan sendiri apakah senioritas layak dikejar.
- Kategori lain dicatat sebagai `checks` dan ikut memengaruhi fit score, tetapi tidak mengubah status: lokasi dan work authorization, kualifikasi (gelar, sertifikasi, lisensi), bahasa, dan batasan eksplisit lain (zona waktu, perjalanan).
- Cakupan geografis (`geo_scope`) tetap dievaluasi terpisah sesuai 3.3.

### 3.3 Aturan

- Jangan menganggap persyaratan terpenuhi bila informasi penting tidak diketahui. Gunakan `needs_review`.
- Persyaratan yang jelas tidak terpenuhi dicatat sebagai alasan dengan kutipan.
- Jangan membuat kesimpulan hukum atau imigrasi.
- Jangan menyamarkan ketidakpastian dengan skor numerik.
- Setiap hasil menyimpan `requirement_id`, kutipan lowongan, dan bukti/deklarasi profil.
- Eligibility tidak memakai priority tier.
- Hanya kutipan persyaratan ber-kind `must_have` yang dapat memblokir; `nice_to_have` selalu informatif.
- Cakupan geografis lowongan (`geo_scope`) dievaluasi terpisah dari `checks`. Nilainya `indonesia`, `worldwide`, `region_locked`, atau `unknown`. Hanya `indonesia` dan `worldwide` yang boleh `eligible`.
- `region_locked` dan `unknown` menghasilkan `needs_review`, bukan `ineligible`, kecuali ada persyaratan wajib lain yang jelas tidak terpenuhi. Lowongan tetap tampil dengan alasan; tidak ada yang disembunyikan.
- `geo_scope` tidak pernah menjadi `checks` dan tidak pernah masuk `fit_score`, karena cakupan adalah fakta tentang lowongan, bukan persyaratan kandidat.
- Region yang disebut di field lokasi mengalahkan kata "anywhere" di deskripsi. "You can work from anywhere within those regions" adalah pembatasan, bukan izin.
- Region yang disebut di judul juga mengikat: `Support Engineer (EMEA - Weekends)` dengan lokasi `Remote, Global` tetap `region_locked`. Judul hanya boleh mempersempit, tidak pernah memperluas. APAC dikecualikan karena mencakup Indonesia.
- `region_locked` yang berada di region terjangkau-relokasi (Asia Tenggara, Australia, Selandia Baru) dan profil menyatakan `relocation` = `conditional`/`yes` tetap `needs_review`, tetapi alasannya menyebut relokasi sebagai pertanyaan terbuka. Lowongan tidak otomatis `eligible`: pemberi kerja belum menyatakan menerima pelamar dari luar negeri. AMER dan EMEA tidak termasuk, karena izin kerja adalah persyaratan terpisah.
- Deterministik dulu; LLM hanya untuk requirement ambigu, dengan kutipan.

### 3.4 Format hasil (konsep)

```json
{
  "job_id": "job_...",
  "job_posting_version_id": "jpv_...",
  "profile_version_id": "prf_...",
  "status": "needs_review",
  "checks": [
    {
      "requirement_id": "req_...",
      "category": "work_authorization",
      "result": "unknown",
      "job_quote": "Must be authorized to work in the EU.",
      "profile_ref": "wa_...",
      "reason": "Profil belum menyatakan status izin kerja untuk EU."
    }
  ]
}
```

### 3.5 Gate `needs_review`

- Pembuatan dokumen diblokir sampai status diselesaikan.
- UI menampilkan informasi yang kurang dan aksi review.
- Status diselesaikan dengan meninjau bukti; bila perlu pengguna melengkapi profil sebagai versi baru lalu menjalankan ulang assessment secara eksplisit.
- Jangan menampilkan aksi utama pembuatan dokumen sebelum status selesai.

### 3.6 Gate `ineligible`

- Tidak ada pembuatan dokumen melalui alur normal.
- Tampilkan alasan dan kutipan persyaratan yang gagal.
- Override (D21) bukan default. Jika dipertahankan: aksi eksplisit terpisah, peringatan, alasan tercatat, status tetap `ineligible`, ranking tidak berubah.

---

## 4. Fit Score

### 4.1 Formula default

```text
must_coverage = bobot must-have terpenuhi / total bobot must-have
nice_coverage = bobot nice-to-have terpenuhi / total bobot nice-to-have
experience_fit = penilaian LLM 0..1, atau 0.5 bila data tidak cukup

fit_score = round(100 * (0.60*must_coverage + 0.15*nice_coverage + 0.25*experience_fit))

if must_coverage < 0.50: verdict = "weak"
elif fit_score >= 75: verdict = "strong"
elif fit_score >= 55: verdict = "moderate"
else: verdict = "weak"
```

### 4.2 Aturan

- Hanya dihitung untuk `eligible`.
- Prioritas dan eligibility tidak masuk formula.
- `verdict` menggambarkan kecocokan, bukan kelayakan.
- Work authorization yang belum diketahui menjadi `needs_review` di eligibility, bukan pengurangan skor.
- Tampilkan komponen skor, bukan hanya angka.
- Sertakan `confidence: low|medium|high` berdasarkan kelengkapan deskripsi dan jumlah requirement eksplisit.
- Setiap komponen dapat ditelusuri ke `requirement_id` dan `evidence_id`.
- Bobot dan ambang adalah rancangan awal; belum ada kalibrasi.
- Jangan mengklaim akurasi sebelum ada validasi.

---

## 5. Ranking

### 5.1 Aturan

- Daftar utama hanya `eligible`, diurutkan `fit_score` menurun.
- `needs_review` di bagian terpisah tanpa fit score sampai diselesaikan.
- `ineligible` di bagian terpisah dengan alasan dan bukti; tidak ada fit score yang dipakai untuk mengurutkan.
- Tie-breaker hanya berlaku bila skor sama atau selisih ≤ `tie_window`.
  - Default `tie_window = 0`: hanya skor identik.
  - Bila dinaikkan, nilai ditampilkan di UI dan berlaku sebagai band, bukan urutan global.
- Di dalam band: tier P1 → P4 (`unclassified` terakhir), lalu `posted_at` terbaru, lalu `job_id` stabil.
- P1 fit rendah tidak boleh mengalahkan P2 fit tinggi di luar band.
- Pengguna dapat mengganti sort ke `priority_tier` secara eksplisit; bukan default dan diberi label.
- Filter/sort tampilan tidak mengubah skor atau eligibility.
- Koreksi tier pengguna disimpan per job lewat `PATCH /api/matches/{job_id}/tier`. Koreksi dipakai pada ranking berikutnya, tidak mengubah fit atau eligibility, dan tidak mengubah ranking run yang sudah tersimpan.

Draft aturan ranking yang dapat dieksekusi ada di [`../phase-00/contracts/ranking.md`](../phase-00/contracts/ranking.md). Aturan produk tetap D13/K10; draft itu belum disetujui.

### 5.2 Rekomendasi

Rekomendasi (`apply_now`, `consider`, `stretch`, `needs_review`, `ineligible`) diturunkan dari eligibility + fit + gap, bukan dari tier.

Ambang rekomendasi belum ditetapkan di master plan. **`OPEN`** untuk Phase 3/4; jangan mengarang ambang final.

### 5.3 Label UI

- `Eligibility: eligible`
- `Fit 78`
- `Prioritas 2 — Global remote`

---

## 6. Input, Output, Dependensi

| Arah | Isi |
|---|---|
| Input | `job_posting_version`, `job_requirement`, `profile_version` confirmed, evidence |
| Output | `eligibility_assessment`, `eligibility_check`, `fit_assessment`, `ranking_run` |
| Dependensi | Discovery (job + requirement), profil confirmed, LLM `classify` untuk requirement ambigu |

Setiap hasil menyimpan `profile_version_id` dan `job_posting_version_id`.

---

## 7. Kontrak dan Schema

Entity: `eligibility_assessment`, `eligibility_check`, `fit_assessment`, `ranking_run` (lihat [`DATABASE.md`](DATABASE.md)).

Field penting:

- `status`, `checks`, `reason`, `confidence`, `status_outdated`
- `fit_score`, `verdict`, `confidence`, komponen, gap, `status_outdated`
- preferensi, `tie_window`, urutan, waktu pada `ranking_run`

Payload API konsep ada di [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) §3.5–3.6.

---

## 8. Error Handling dan State

| Kondisi | Perilaku |
|---|---|
| Requirement ambigu | `needs_review`, bukan tebakan |
| Requirement tidak ditemukan | Minimal 1 must-have wajib; bila tidak ada, laporkan |
| Profil tidak confirmed | Tolak assessment |
| Fit diminta untuk non-eligible | Tolak; jangan hitung |
| Tier berubah | Fit tidak berubah; ranking boleh berubah hanya dalam band |
| Profil/job version berubah | Tandai `Outdated`; jangan hitung ulang otomatis |
| Assessment gagal setelah fetch | Run `partial` + `assessment_failed`; job tersimpan |
| LLM gagal | `needs_review` atau error jelas; jangan menebak |

---

## 9. Keamanan dan Privasi

- Kutipan dan bukti wajib; jangan mengarang.
- Jangan membuat kesimpulan hukum/imigrasi.
- Jangan mengirim seluruh profil ke LLM; kirim irisan relevan.
- Log tanpa isi profil/PII.
- Jangan menampilkan skor sebagai bukti kelayakan.

---

## 10. Acceptance dan Verifikasi

Mengacu `PLAN.md` §14:

- Kriteria 7: setiap job punya status + alasan + bukti; `needs_review` bukan eligible; `ineligible` terpisah.
- Kriteria 8: gate `needs_review` memblokir dokumen.
- Kriteria 9: gate `ineligible`; override hanya eksplisit bila D21 dipertahankan.
- Kriteria 12: ranking fit-first; tier hanya tie-break; ubah tier tidak mengubah fit; P1 rendah tidak mengalahkan P2 tinggi.
- Kriteria 13: fit hanya untuk eligible.

Verifikasi:

- Test fixture eligibility untuk ketiga status.
- Test invariant: tier swap tidak mengubah fit.
- Test ranking: tie hanya dalam window.
- Test gate: dokumen ditolak untuk `needs_review`/`ineligible`.
- Test kutipan/bukti wajib.

---

## 11. Keputusan dan `OPEN`

Final: K10, K11, K23; D13, D14, D15, D16.

`OPEN`:

- D21 (override `ineligible`).
- Ambang rekomendasi.
- Kalibrasi bobot dan ambang fit.
- Apakah `experience_fit` default 0.5 selalu tepat.

Jangan mengubah formula atau status tanpa keputusan pengguna.

---

## 12. Referensi PLAN.md

- §4.2 Eligibility gate
- §4.2 Ranking
- §4.2 Fit score
- §4.2 Klasifikasi priority tier (D15, D16)
- §9.4 snapshot `priority_tier`, `eligibility_status`, `fit_score`
- §13 Phase 3 dan Phase 4
- §14 kriteria 7–9, 12–13
- §15.4 D13–D16, D21
