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
  "access_method": "ats_api | aggregator | html | manual_url",
  "ats": "greenhouse | lever | ashby | unknown",
  "verification_status": "unverified | verified | restricted | broken",
  "tos_notes": "...",
  "last_checked_at": null,
  "last_success_at": null,
  "health_status": "unknown | healthy | degraded | broken",
  "consecutive_failures": 0,
  "last_error_code": null,
  "next_run_at": null,
  "priority_order": 100,
  "fetch_interval_minutes": 360,
  "daily_request_quota": 24,
  "requests_last_24h": 0,
  "stale": false,
  "enabled": true
}
```

Operasi UI: tambah, edit, nonaktifkan, ubah status verifikasi, atur prioritas/interval/kuota.

`access_method` yang boleh dibuat pengguna hanya `ats_api` (board satu perusahaan yang punya adapter). `html` ditolak saat write karena tidak ada adapter yang dapat mengambilnya; menyimpannya hanya menjanjikan fetch yang selalu di-skip. `aggregator` juga ditolak sejak 2026-10-23: satu-satunya adapter feed (Himalayas) dihapus dari daftar sumber. Baris lama bertipe `html`/`aggregator` tetap terbaca dan dapat dinonaktifkan, tetapi tidak pernah di-fetch.

### Kesehatan dan penjadwalan

`health_status` adalah turunan streak kegagalan, bukan penilaian terpisah:

| Status | Arti |
|---|---|
| `unknown` | Belum ada percobaan |
| `healthy` | Percobaan terakhir sukses |
| `degraded` | 1-2 kegagalan berurutan |
| `broken` | 3 atau lebih kegagalan berurutan |

- Kegagalan memberi backoff eksponensial: `interval × 2^(failure-1)`, maksimum faktor 8. `Retry-After` dari server dipakai sebagai lantai jadwal, bukan pengganti interval.
- Sukses mereset `consecutive_failures` ke 0 dan menjadwalkan `next_run_at = now + fetch_interval_minutes`.
- `daily_request_quota` membatasi jumlah HTTP request per 24 jam, dihitung dari `SUM(discovery_run_source.request_count)` dengan predikat `last_attempt_at` dalam 24 jam terakhir. Setiap percobaan mencatat request yang benar-benar dipakai, jadi sukses, 304, dan kegagalan semuanya dihitung, dan adapter berhalaman menghitung satu per halaman. `0` berarti tanpa batas. Sumber `skipped` dengan `source_quota_exhausted` bila sisa kuota tidak cukup untuk seluruh kebutuhan run; snapshot sebagian tidak pernah dipakai.
- Scheduler latar bersifat opt-in (`[discovery] scheduler_enabled = true`, default mati). Tanpa itu, run hanya terjadi saat pengguna menekan tombol.
- `partial_snapshot`: adapter yang hanya mengembalikan sebagian board menandai `ParsedJobs.complete = False`; run tidak menutup lowongan yang tidak terlihat pada snapshot itu.

### Seed

- Target sekitar **20 perusahaan** Indonesia dan global (K12, D3).
- Target perencanaan, bukan cakupan terverifikasi.
- **Disetujui 2026-10-21 (D3, global-only):** GitLab (Greenhouse), Stripe (Greenhouse), Binance (Lever), Linear (Ashby), PostHog (Ashby), Supabase (Ashby). Sumber dibuat lewat registry/UI, bukan migrasi.
- **Tetap nonaktif:** Xendit (Greenhouse), Amartha (Workable), Ajaib (Workable) sampai D17 dan persetujuan ToS/atribusi. Workable belum punya adapter.
- Daftar final ~20 belum ada dan harus diisi/dikonfirmasi pengguna.

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

Semua aggregator di atas remote/EU/US-centric. Tidak satu pun menyediakan cakupan Indonesia yang memadai.

#### Feed tanpa adapter (termasuk Himalayas)

Himalayas dihapus dari daftar sumber yang didukung pada 2026-10-23. Dokumentasi API-nya meminta lowongan tidak aktif dihapus, tanpa menjelaskan apakah artinya hapus salinan lokal atau cukup disembunyikan. Pengguna memutuskan tidak mengejar klarifikasi dan tidak memakai sumber ini.

Konsekuensinya:

- Tidak ada `access_method = aggregator` yang dapat dibuat pengguna. Nilai yang boleh ditulis hanya `ats_api`.
- Adapter `himalayas.py`, fixture, test, opsi UI, atribusi UI, dan `GAWE_HIMALAYAS_API_KEY` dihapus.
- Pagination generik (`fetch_pages`, `parse_pages`, manifest halaman) ikut dihapus karena tidak ada adapter yang memakainya. Feed Phase 5 menambahkannya kembali bersama adapter dan test-nya. Kontrak snapshot parsial (`ParsedJobs.complete`, `skip_reasons`) tetap ada.
- Baris registry lama bertipe `aggregator` atau `html` tetap dapat dibaca dan dinonaktifkan, tetapi tidak pernah di-fetch.

Keputusan: [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) D3 dan "Blocker ditutup".

### 4.6 Sumber `browser` (sesi login pengguna)

Jalur ini ada karena jobboard besar (Indeed, Jobstreet, LinkedIn) tidak menyediakan API lowongan publik dan menolak fetch anonim. Jalur ini **bukan crawler publik** dan **bukan bypass**: sistem memakai sesi login yang pengguna sendiri buat di profil Chromium lokal.

Aturan:

- Hanya Playwright yang dijalankan **headed** untuk login. Run crawl berjalan **headless** dengan profil yang sama.
- Profil disimpan di `%LOCALAPPDATA%\Gawe\browser-profile`, di luar repo dan di luar DB. Tidak pernah masuk backup, log, atau respons API.
- Password dan 2FA tidak pernah menyentuh Gawe. Pengguna login manual di jendela Chromium yang dibuka Gawe.
- Cookie sesi tidak dibaca, tidak dicetak, dan tidak dikirim ke klien.
- Jalur ini tidak memeriksa `robots.txt`: aturan itu berlaku untuk fetch anonim, sedangkan di sini permintaan datang dari sesi pengguna yang login atas namanya sendiri. Pengecualian ini dicatat di [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md) §4.2.
- Crawler hanya membuka halaman daftar lowongan dan halaman detail lowongan. Tidak mengisi form, tidak menekan Apply, tidak mengirim pesan, tidak mengubah profil.
- Saat CAPTCHA, halaman login, atau 403 terdeteksi: run berhenti untuk sumber itu dengan status `browser_blocked`, tanpa retry otomatis. Pengguna yang memutuskan kapan mencoba lagi.
- Batas per run: jumlah kartu, jumlah halaman detail, dan timeout per halaman disimpan sebagai konfigurasi sumber. Nilai default ditetapkan di implementasi, bukan di dokumen ini.
- ToS tiap situs berlaku pada akun pengguna. Risiko pembatasan akun ditanggung pengguna dan dicatat per sumber di `tos_notes`.
- Tidak ada klaim cakupan. Sumber `browser` hanya menambah lowongan yang berhasil dibaca pada run terakhir.

Kontrak adapter tetap: `build_url(source)` + `parse(html, source)` menghasilkan `ParsedJobs(jobs, skipped, complete)`. Dedupe, eligibility, ranking, dan approval tidak berubah.

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
| URL manual | Satu lowongan; validasi per request; **fallback**, bukan jalur utama; dapat memakai teks tempel bila halaman menolak akses atau dirender JavaScript |
| Himalayas | Dihapus 2026-10-23: API mewajibkan penghapusan lowongan tidak aktif tanpa menjelaskan cakupannya, dan klarifikasi tidak dikejar. Adapter dan konfigurasinya ikut dihapus. |

### 4.5 Catatan cakupan

- ATS API bukan mesin pencari lowongan umum.
- Tidak ada sumber dengan API resmi yang memberi cakupan Indonesia luas.
- Cakupan Indonesia bergantung pada daftar perusahaan Indonesia yang memakai ATS tersebut (D3) dan verifikasi sumber (D17).
- Jangan mengklaim cakupan Indonesia sebelum D17 tersedia dan sumber diuji.
- Sumber tanpa API resmi tidak di-scrape lewat HTTP biasa; gunakan fallback URL manual. Pengecualian: sumber bertipe `browser` (§4.6) memakai sesi login pengguna sendiri, atas perintah eksplisit, dan tanpa klaim cakupan.

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
- Completeness flag untuk metadata yang hilang. Dua nilai yang tampil di UI: `company_name` → "Nama perusahaan dari slug" (nama perusahaan diambil dari slug `guid` karena payload tidak memuat `companyName`), dan `posted_at` → "Tanggal posting tidak tersedia" (sumber tidak mempublikasikan tanggal posting).
- `fetched_at` disimpan; warning bila data >7 hari.
- Greenhouse `content` adalah HTML ter-escape ganda; perlu `html.unescape` dua kali (quirk terverifikasi).
- Simpan `source_id` dan URL asli lowongan (`canonical_url`) pada setiap job. Tidak ada job tanpa sumber.
- `market` pada job adalah nilai turunan dari `geo_scope`, bukan field yang diisi adapter: `indonesia` → `indonesia`, `worldwide` → `global`, sisanya `unknown`. Sebelumnya `market` hanya terisi bila field lokasi memuat kata "indonesia", sehingga seluruh 102 job tersimpan `unknown` dan filter Pasar di Job Matches tidak pernah menyaring apa pun.

---

## 8. Dedupe

- Exact: `(source, source_job_id)` dan `canonical_url`.
- Lintas sumber: fingerprint `sha256(company_norm + title_norm + location_norm + employment_type)`.
- `location_norm` adalah `location_key`: segmen lokasi pertama yang benar-benar menamai tempat. Kata mode kerja (`remote`, `anywhere`, `hybrid`, `onsite`, `global`) dilewati karena tidak menamai tempat. Tanpa aturan ini `city_of("Remote, AMER")` dan `city_of("Remote, EMEA")` sama-sama `remote`, sehingga dua lowongan regional yang berbeda tergabung.
- Fuzzy: `difflib.SequenceMatcher` dalam blok company/location yang sama, threshold 0.92. Dua judul yang menyebut region berbeda (`AMER` vs `EMEA`) tidak pernah digabung, meski rasionya tinggi.
- Fingerprint adalah nilai turunan. Setiap kali normalisasi berubah, fingerprint baris lama harus dihitung ulang; kalau tidak, dedupe lintas sumber melewatkan pasangan lama-baru.
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

- Tanpa CAPTCHA bypass, tanpa paywall bypass, tanpa rotasi proxy.
- Jalur `ats_api` dan fetch HTML umum berjalan tanpa login. Jalur `browser` (lihat §4.6) memakai sesi login pengguna sendiri di profil Chromium lokal; hanya bisa dijalankan atas perintah eksplisit pengguna. Tidak ada login otomatis dari password tersimpan, tidak ada penyamaran identitas browser, dan tidak ada percobaan ulang otomatis setelah diblokir.
- 403/429 → berhenti untuk sumber itu, laporkan.
- `robots.txt` dicek untuk fetch HTML umum.
- Bila halaman URL manual menolak akses otomatis (403/429) atau dirender JavaScript, pengguna dapat menempelkan teks lowongan. URL tetap wajib dan tetap divalidasi karena menjadi identitas job dan target Apply; teks tempel tidak di-fetch, sehingga `robots.txt` tidak berlaku untuk jalur itu.
- Cache 24 jam; jangan polling melebihi batas sumber.
- Fetch kondisional dipakai bila sumber mendukung: kirim `If-None-Match` berisi `ETag` snapshot terakhir. Balasan `304 Not Modified` berarti papan tidak berubah, jadi payload tidak diunduh, tidak diparse, dan lowongan **tidak** ditutup. Hanya baris `source_fetch` dengan payload penuh yang menyimpan `etag`.
- `304` bukan kegagalan dan bukan snapshot kosong. Jangan pernah memperlakukannya sebagai "semua lowongan hilang".
- Attribution ditampilkan untuk sumber yang mensyaratkannya (Remotive, Jobicy, Arbeitnow bila disyaratkan).
- Setiap sumber menyimpan catatan ToS dan status verifikasi.
- Hanya sumber dengan dokumentasi akses resmi yang boleh diimplementasikan.

---

## 11. Error Handling dan State

| Kondisi | Perilaku |
|---|---|
| Satu sumber gagal | Jangan hapus hasil sukses; status per sumber; retry |
| 403/429 | Berhenti untuk sumber itu; laporkan |
| CAPTCHA atau halaman login (sumber `browser`) | Berhenti untuk sumber itu; status `browser_blocked`; minta pengguna login ulang; tidak ada retry otomatis |
| Sesi browser kedaluwarsa | Berhenti sebelum fetch; status `session_expired`; minta pengguna login ulang |
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

Final: K1, K2, K12, K18; D2, D15, D16, D6. D3 diputuskan sebagian (global-only, 2026-10-21).

`OPEN`: D3 (daftar final ~20 dan sumber Indonesia), D17 (sumber Indonesia), D11 (API berbayar), D10 (retensi cache), D9 (reviewer model terpisah).

---

## 14. Referensi PLAN.md

- §4.2 `/scrape` (prasyarat, preferensi, source registry, pipeline, normalisasi, dedupe, tier, etika)
- §9.2 entity `source_registry`, `job`, `job_posting_version`
- §11 SSRF, scraping kedaluwarsa
- §13 Phase 3 dan Phase 4
- §14 kriteria 6 dan 12
