# JOB-DISCOVERY — Sumber, Fetch, Normalisasi, dan Dedupe

**Domain:** sumber lowongan, pengambilan, normalisasi, deduplikasi, source verification, klasifikasi priority tier.
**Source of Truth terkait:** [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md) (definisi tier), [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md) (URL/SSRF), [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) (D3, D17).
**Referensi master:** `PLAN.md` §4.2, §11, §13 Phase 3.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Source registry dan status verifikasi.
- Adapter per sumber.
- Fetch dengan rate limit dan etika akses.
- Normalisasi field.
- Penyimpanan versi deskripsi lowongan.
- Dedupe.
- Penandaan lowongan tertutup/kedaluwarsa.
- Klasifikasi priority tier dan alasan/confidence.

**Tidak bertanggung jawab:**

- Eligibility gate dan fit score (domain eligibility).
- Ranking (domain eligibility).
- Pembuatan dokumen.
- Menentukan sumber Indonesia final (D17).

Discovery otomatis adalah jalur utama produk. URL manual adalah fallback opsional dan memakai sumber sintetis `manual_url`.

---

## 2. Prasyarat

1. Ada profil aktif berstatus `confirmed`.
2. `profile_version_id` dicatat pada setiap run discovery dan assessment.
3. Bila belum ada profil confirmed, halaman discovery hanya menampilkan status dan tautan ke setup. Tidak ada fetch lowongan.
4. Setidaknya satu entri registry `verified` dan `enabled`, atau pengguna memakai fallback URL manual.

Gate ini ditegakkan di backend, bukan hanya UI.

---

## 3. Source Registry

Setiap sumber adalah record yang dapat dikelola dari web UI:

```json
{
  "source_id": "src_...",
  "company": "...",
  "market": "indonesia | global",
  "careers_url": "...",
  "access_method": "ats_api | html | manual_url",
  "ats": "greenhouse | lever | ashby | unknown",
  "verification_status": "unverified | verified | restricted | broken",
  "tos_notes": "...",
  "last_checked_at": null,
  "enabled": true
}
```

Operasi UI: tambah, edit, nonaktifkan, ubah status verifikasi.

### Seed

- Target sekitar **20 perusahaan** Indonesia dan global (K12, D3).
- Target perencanaan, bukan cakupan terverifikasi.
- Daftar final belum ada dan harus diisi/dikonfirmasi pengguna.

### Status verifikasi

| Status | Arti |
|---|---|
| `unverified` | Belum diuji |
| `verified` | Sudah diuji dan dapat dipakai |
| `restricted` | Ada batasan akses/ToS |
| `broken` | Tidak berfungsi |

Sumber yang tidak jelas dilarang diaktifkan tanpa review pengguna.

---

## 4. Sumber dan Status Verifikasi

Status kolom "Bukti" menyatakan tingkat verifikasi dokumentasi, bukan jaminan ketersediaan atau legalitas penggunaan.

### 4.1 ATS dengan API publik tanpa auth

| Sumber | Endpoint | Cakupan | Batas | Bukti |
|---|---|---|---|---|
| Greenhouse Job Board API | `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` (`?content=true`) | Per perusahaan pengguna Greenhouse | Tanpa auth; hanya per board; tidak ada pencarian lintas perusahaan; `content` HTML ter-escape ganda | Dokumentasi resmi `developers.greenhouse.io/job-board.html` |
| Lever Postings API | `GET https://api.lever.co/v0/postings/{site}?mode=json` (EU: `api.eu.lever.co`) | Per perusahaan pengguna Lever | Tanpa auth; hanya per site; tidak ada endpoint lintas perusahaan atau full-text search | Dokumentasi resmi `github.com/lever/postings-api` |
| Ashby Job Postings API | `GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation=true` | Per organisasi pengguna Ashby | Tanpa auth; hanya per job board; field `isListed`, `workplaceType`, `employmentType`, `publishedAt` | Dokumentasi resmi `developers.ashbyhq.com` |

Ketiganya per-perusahaan. Cakupan luas membutuhkan daftar perusahaan (D3) yang dikurasi.

### 4.2 ATS/HR platform dengan syarat tambahan

| Sumber | Endpoint | Syarat | Status |
|---|---|---|---|
| SmartRecruiters Posting API | `GET /v1/companies/{companyIdentifier}/postings` | API key atau OAuth; Job Board API partner-only | Butuh kredensial; belum disetujui |
| Workable careers widget | `GET https://apply.workable.com/api/v1/widget/accounts/{account}?details=true` | Tanpa key; rate limit per IP; endpoint widget, bukan API publik penuh | Terdokumentasi di help center Workable |
| Recruitee Careers Site API | `GET https://{company}.recruitee.com/api/...` | Butuh API token; perspektif kandidat | Belum disetujui |
| Personio XML | `GET https://{account}.jobs.personio.com/xml?language=en` | Publik; XML; fokus DACH | Di luar prioritas pasar |

### 4.3 Agregator remote/EU

| Sumber | Endpoint | Batas | Bukti |
|---|---|---|---|
| Arbeitnow | `GET https://www.arbeitnow.com/api/job-board-api` | Tanpa key; board Jerman/EU; pagination; board penuh besar | Dokumentasi Postman resmi |
| Remotive | `GET https://remotive.com/api/remote-jobs` | Tanpa key; maks ~4 req/hari; delay 24 jam; attribution + link-back wajib; tanpa redistribusi ke board pihak ketiga | `github.com/remotive-com/remote-jobs-api` |
| Jobicy | `GET https://jobicy.com/api/v2/remote-jobs` | Tanpa key; jendela 7 hari; cursor; attribution; maks 1 poll/jam; batch status `/api/v2/remote-jobs/status?ids=` | `jobicy.com/jobs-rss-feed` |
| Himalayas | `GET https://himalayas.app/jobs/api` (cursor, maks 20) dan `/jobs/api/search` | Tanpa key untuk dasar; free key 60/menit & 10k/hari; attribution; tanpa redistribusi; tanpa CORS | `himalayas.app/api`, OpenAPI resmi |

Semua aggregator di atas remote/EU/US-centric. Tidak satu pun menyediakan cakupan Indonesia yang memadai.

### 4.4 Sumber yang tidak dapat dipakai v1

| Sumber | Alasan |
|---|---|
| Adzuna | Butuh key; ~250 call/hari gratis; tidak mencakup Indonesia (D11: tidak untuk v1) |
| Jooble | Key per domain negara; formulir review |
| SEEK / Jobstreet | Akses butuh persetujuan Integration Request |
| Kalibrr | API integrasi hanya untuk pelanggan, lewat Account Manager |
| Glints, Dealls | Tidak ada API lowongan publik resmi yang ditemukan |
| Karirhub (Kemnaker) | Integrasi API dengan mitra disebut ada; tidak ada API developer publik terdokumentasi |
| Workday | Tidak ada API job posting publik; REST/SOAP per tenant |
| LinkedIn, Indeed | Anti-bot/auth/ToS; tidak didukung |
| Halaman karier perusahaan (HTML) | Satu perusahaan; tergantung robots/ToS; perlu verifikasi per situs |
| URL manual | Satu lowongan; validasi per request; **fallback**, bukan jalur utama |

### 4.5 Catatan cakupan

- ATS API bukan mesin pencari lowongan umum.
- Tidak ada sumber dengan API resmi yang memberi cakupan Indonesia luas.
- Cakupan Indonesia bergantung pada daftar perusahaan Indonesia yang memakai ATS tersebut (D3) dan verifikasi sumber (D17).
- Jangan mengklaim cakupan Indonesia sebelum D17 tersedia dan sumber diuji.
- Sumber tanpa API resmi tidak di-scrape; gunakan fallback URL manual.

---

## 5. Preferensi

```json
{
  "keywords": ["backend engineer", "python"],
  "exclude_keywords": ["sales", "intern"],
  "target_markets": ["global", "indonesia"],
  "locations": ["Jakarta", "Remote"],
  "work_modes": ["onsite", "remote", "hybrid"],
  "seniority": ["mid", "senior"],
  "employment_types": ["full_time"],
  "max_age_days": 30,
  "min_fit_score": 0,
  "ranking": {
    "primary": "fit_score_desc",
    "tie_breaker": ["priority_tier", "posted_at_desc", "job_id"],
    "tie_window": 0
  },
  "sources": ["source_id_..."],
  "include_ineligible_in_view": true
}
```

`min_fit_score` default 0. Bila diubah, UI menampilkan jumlah yang tersembunyi.

---

## 6. Pipeline

1. Muat profil confirmed + preferensi + source registry yang enabled.
2. Jalankan adapter per sumber, paralel maksimal 3, rate limit 1 request/detik per host.
3. Simpan respons mentah + hash + `fetched_at` + `source_id` + `verification_status` saat itu.
4. Normalisasi field: judul, perusahaan, lokasi, remote, tipe kerja, seniority, gaji, tanggal, deskripsi, URL kanonik.
5. Simpan `job_posting_version` dengan `content_hash`.
6. Dedupe.
7. Tandai lowongan tertutup/kedaluwarsa.
8. Klasifikasi priority tier dari lokasi dan mode kerja, dengan alasan dan confidence.
9. Ekstrak requirement (must-have, nice-to-have, responsibility, eligibility constraints).
10. Eligibility gate per lowongan.
11. Fit score hanya untuk `eligible`.
12. Ranking fit-first.
13. Tampilkan daftar + alasan + gap + bukti; `needs_review` dan `ineligible` terpisah.
14. Pengguna pilih job → `/apply`, atau memakai fallback URL manual.

---

## 7. Normalisasi

- URL kanonik: buang `utm_*`, `gh_src`, `ref`, trailing slash; simpan URL final setelah redirect.
- Field wajib: judul, perusahaan, deskripsi.
- Completeness flag untuk metadata yang hilang.
- `fetched_at` disimpan; warning bila data >7 hari.
- Greenhouse `content` adalah HTML ter-escape ganda; perlu `html.unescape` dua kali (quirk terverifikasi).
- Simpan `source_id` dan URL asli lowongan (`canonical_url`) pada setiap job. Tidak ada job tanpa sumber.

---

## 8. Dedupe

- Exact: `(source, source_job_id)` dan `canonical_url`.
- Lintas sumber: fingerprint `sha256(company_norm + title_norm + city_norm + employment_type)`.
- Fuzzy: `difflib.SequenceMatcher` dalam blok company/location yang sama, threshold 0.92.
- Simpan `duplicate_of`; jangan hapus data.
- Hindari duplikasi saat run diulang (idempoten).
- Lowongan tertutup tetap tersimpan dengan status `closed`/`expired`; tidak dihapus.

---

## 9. Klasifikasi Priority Tier

Definisi tier ada di [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md) §5.1.

Aturan:

- Pakai field terstruktur bila tersedia.
- Bila hanya teks bebas, LLM boleh membantu; output wajib menyertakan kutipan dan alasan.
- Bila metadata tidak cukup, hasil `unclassified`; jangan mengarang tier.
- Prioritas adalah preferensi pengguna, bukan bukti kelayakan.
- Pengguna dapat mengoreksi tier; koreksi disimpan dan dipakai untuk ranking berikutnya.
- `priority_tier` disimpan sebagai snapshot pada job dan assessment.

### D15 — Hybrid

- Hybrid diklasifikasikan onsite.
- UI menampilkan lokasi kantor, jadwal, dan kewajiban kehadiran bila tersedia.
- Jangan menyebut hybrid sebagai remote penuh.

### D16 — Global remote

- P2 hanya bila sumber mendukung bahwa kandidat dari Indonesia atau worldwide diterima.
- Label "remote" saja tidak cukup.
- Remote yang dibatasi negara/wilayah tidak otomatis P2; bisa P4, `unclassified`, atau `needs_review`.
- Bila batasan belum jelas, tandai `needs_review` dan tampilkan alasannya.

---

## 10. Etika Akses

- Tanpa login, tanpa CAPTCHA bypass, tanpa paywall bypass, tanpa rotasi proxy.
- 403/429 → berhenti untuk sumber itu, laporkan.
- `robots.txt` dicek untuk fetch HTML umum.
- Cache 24 jam; jangan polling melebihi batas sumber.
- Attribution ditampilkan untuk sumber yang mensyaratkannya (Remotive, Jobicy, Himalayas, Arbeitnow bila disyaratkan).
- Setiap sumber menyimpan catatan ToS dan status verifikasi.
- Hanya sumber dengan dokumentasi akses resmi yang boleh diimplementasikan.

---

## 11. Error Handling dan State

| Kondisi | Perilaku |
|---|---|
| Satu sumber gagal | Jangan hapus hasil sukses; status per sumber; retry |
| 403/429 | Berhenti untuk sumber itu; laporkan |
| Data minimal tidak lengkap | Tandai; jangan analisis sebagai lengkap |
| Data >7 hari | Warning |
| Lowongan tertutup/kedaluwarsa | Tandai `closed`/`expired`; simpan; bukan kegagalan sumber |
| Duplikat | Simpan `duplicate_of` |
| Metadata lokasi kurang | `unclassified` atau `needs_review` |
| Sumber belum verified | Jangan aktifkan tanpa review |

Status per sumber: `queued`, `processing`, `completed`, `partial`, `failed`, `skipped` (kontrak di [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) §4.3).

---

## 12. Acceptance dan Verifikasi

Mengacu `PLAN.md` §13 Phase 3 dan §14 kriteria 6, 12:

- Minimal dua adapter ATS berjalan dengan contract test.
- Seed dapat ditambah/edit/nonaktifkan.
- Sumber `unverified`/`restricted`/nonaktif tidak di-fetch.
- `profile_version_id` tercatat; 0 fetch tanpa profil confirmed.
- Rate limit dan paralel maks 3 dipatuhi.
- Hasil parsial tidak dihapus saat sumber lain gagal.
- Dedupe exact + lintas sumber + fuzzy teruji; run ulang idempoten.
- Setiap job menyimpan `source_id` dan `canonical_url`.
- Lowongan tertutup ditandai, tidak dihapus.
- Status verifikasi dan waktu fetch terlihat.
- `needs_review` dan `ineligible` terpisah.
- Urutan fit-first; tier hanya tie-break.
- `fit_score` tidak berubah saat tier diubah.
- Filter/sort tidak mengubah skor.

Verifikasi: contract test adapter dengan respons fixture tersimpan, test dedupe, test klasifikasi, test invariant ranking, uji live terbatas pada sumber yang disetujui.

**Klaim cakupan Indonesia tidak boleh dibuat sebelum D17 tersedia dan sumber diuji.**

---

## 13. Keputusan dan `OPEN`

Final: K1, K2, K12, K18; D2, D15, D16.

`OPEN`: D3 (daftar seed), D17 (sumber Indonesia), D11 (API berbayar), D10 (retensi cache).

---

## 14. Referensi PLAN.md

- §4.2 `/scrape` (prasyarat, preferensi, source registry, pipeline, normalisasi, dedupe, tier, etika)
- §9.2 entity `source_registry`, `job`, `job_posting_version`
- §11 SSRF, scraping kedaluwarsa
- §13 Phase 3 dan Phase 4
- §14 kriteria 6 dan 12
