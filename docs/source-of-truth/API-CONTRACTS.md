# API-CONTRACTS — Kontrak Frontend/Backend

**Source of Truth untuk:** kontrak endpoint dan payload lintas frontend/backend.
**Bukan Source of Truth untuk:** schema database internal (lihat [`../domains/DATABASE.md`](../domains/DATABASE.md)), aturan bisnis (lihat [`PRODUCT.md`](PRODUCT.md)).
**Referensi master:** `PLAN.md` §4.0 A0, §4.1, §4.2, §4.3, §6, §8, §9, §12.

> **Status kontrak:** disetujui pengguna 2026-10-19 pada Phase 0. C4 (endpoint API) ditutup. Draft final ada di [`../phase-00/contracts/openapi.yaml`](../phase-00/contracts/openapi.yaml).
>
> Kontrak ini menjadi acuan final Phase 1. Perubahan isi kontrak setelah persetujuan memerlukan persetujuan pengguna baru dan pembaruan [`DECISIONS.md`](DECISIONS.md).
>
> **Batasan yang tetap berlaku:** D10, D20, D21, ambang rekomendasi, kalibrasi bobot fit, dan port runtime final tetap `OPEN`. D1 sudah diputuskan 2026-10-19 (9Router lewat `openai_compatible`) dan D6 sudah diputuskan 2026-10-21 (Tectonic untuk PDF); kontrak ini tidak mengubah status keputusan mana pun.

---

## 1. Prinsip Kontrak

1. Frontend dan backend berkomunikasi hanya lewat **API JSON**.
2. Backend adalah sumber kebenaran untuk eligibility, fit score, ranking, approval, status, dan nama file final.
3. Frontend tidak mengakses database atau filesystem langsung.
4. Skema OpenAPI dihasilkan backend. Tipe TypeScript request/response dihasilkan dari OpenAPI, bukan ditulis ulang manual.
5. Typecheck adalah gate: perubahan kontrak yang merusak harus terdeteksi.
6. Request yang mengubah state wajib menyertakan CSRF token.
7. Konten job dikirim sebagai data dan dirender sebagai teks; HTML disanitasi di backend atau dengan sanitizer.
8. Error tidak boleh memuat PII, isi dokumen, prompt, respons model, atau secret.
9. Respons yang memuat nilai otoritatif harus menyertakan ID versi/hash yang dipakai.
10. Tidak ada endpoint yang melakukan submit lamaran otomatis.
11. Field otoritatif bersifat read-only bagi klien. Klien tidak boleh mengirim eligibility, fit score, ranking, approval, status, atau nama file final sebagai input yang mengubah hasil.
12. Tidak ada endpoint di luar kebutuhan halaman yang terdokumentasi di [`UI-DESIGN.md`](UI-DESIGN.md) §3 dan workflow [`PRODUCT.md`](PRODUCT.md) §4.

---

## 2. Route Group dan Inventaris Endpoint

Sumber route group: `PLAN.md` §12 mapping workflow. Endpoint detail ditetapkan di sini dan di draft OpenAPI.

Base URL: origin runtime. Klien memakai origin tempat UI disajikan, atau origin API `http://127.0.0.1:<port>` pada runtime lokal. Bind wajib `127.0.0.1`. Port final belum ditetapkan (`OPEN`, bukan keputusan produk); `8000` hanya contoh dokumentasi, bukan persyaratan kontrak. Draft OpenAPI memakai `servers[0].url: /` (relatif) supaya port tidak menjadi bagian kontrak.

Konvensi umum:

- Semua request dan response `application/json; charset=utf-8`, kecuali unggah `multipart/form-data` dan unduhan file biner.
- ID adalah string opaque dengan prefix tampilan (`job_7f3a2c91`). Klien tidak boleh mem-parsing ID.
- Hash adalah SHA-256 hex huruf kecil.
- Waktu adalah ISO 8601 UTC (`2026-10-19T10:00:00Z`).
- Nama field memakai `snake_case`.
- Enum bersifat tertutup. Nilai baru ditambahkan lewat perubahan kontrak, bukan diterima diam-diam.

### 2.1 Session dan Overview

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/session` | `getSession` | Ambil session + token CSRF |
| GET | `/api/overview` | `getOverview` | Ringkasan status, hitungan, next action |
| GET | `/api/overview/activity` | `listActivity` | Aktivitas terbaru (metadata aman) |

### 2.2 Setup (`/master-cv`)

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/setup/master-cv` | `getMasterCv` | Master CV aktif |
| POST | `/api/setup/master-cv` | `uploadMasterCv` | Unggah Master CV |
| GET | `/api/setup/master-cv/file` | `downloadMasterCv` | Unduh file asli |
| POST | `/api/setup/master-cv/extractions` | `startProfileExtraction` | Jalankan ekstraksi profil (task) |
| GET | `/api/setup/profiles` | `listProfileVersions` | Riwayat versi profil |
| GET | `/api/setup/profiles/{profile_version_id}` | `getProfileVersion` | Detail versi profil |
| PATCH | `/api/setup/profiles/{profile_version_id}` | `correctProfileVersion` | Kirim koreksi profil |
| POST | `/api/setup/profiles/{profile_version_id}/confirm` | `confirmProfileVersion` | Konfirmasi versi profil |
| POST | `/api/setup/profile/rollback` | `rollbackProfile` | Rollback ke versi confirmed sebelumnya |

### 2.3 Discovery (`/discovery`)

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/discovery/runs` | `listDiscoveryRuns` | Riwayat run discovery |
| POST | `/api/discovery/runs` | `startDiscoveryRun` | Mulai run discovery (task) |
| GET | `/api/discovery/runs/{run_id}` | `getDiscoveryRun` | Status + hasil per sumber |

### 2.4 Job Matches (`/matches`)

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/matches` | `listMatches` | Daftar job teranking + filter/sort |
| GET | `/api/matches/{job_id}` | `getMatch` | Detail job untuk side panel |
| PATCH | `/api/matches/{job_id}/tier` | `overrideMatchTier` | Koreksi priority tier pengguna |

### 2.5 Applications (`/applications`, `/applications/:id`)

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/applications` | `listApplications` | Daftar workspace |
| POST | `/api/applications` | `createApplication` | Buat workspace dari `job_id` atau `url` |
| GET | `/api/applications/{application_id}` | `getApplication` | Detail workspace + next action |
| GET | `/api/applications/{application_id}/job` | `getApplicationJob` | Job + versi deskripsi yang dianalisis |
| POST | `/api/applications/{application_id}/analysis` | `rerunApplicationAnalysis` | Analisis ulang eksplisit (task) |
| GET | `/api/applications/{application_id}/eligibility` | `getEligibility` | Eligibility assessment |
| GET | `/api/applications/{application_id}/fit` | `getFitAssessment` | Fit assessment (hanya `eligible`) |

### 2.6 Dokumen, Review, Approval

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/applications/{application_id}/documents` | `listDocuments` | Daftar versi CV/CL |
| POST | `/api/applications/{application_id}/documents` | `generateDocuments` | Hasilkan versi baru (task) |
| GET | `/api/applications/{application_id}/documents/{document_version_id}` | `getDocumentVersion` | Detail versi + diff |
| POST | `/api/applications/{application_id}/documents/{document_version_id}/revisions` | `createDocumentRevision` | Edit → versi baru |
| POST | `/api/applications/{application_id}/documents/{document_version_id}/regenerate` | `regenerateDocument` | Regenerate → versi baru (task) |
| POST | `/api/applications/{application_id}/documents/{document_version_id}/review` | `runDocumentReview` | Jalankan reviewer (task) |
| GET | `/api/applications/{application_id}/documents/{document_version_id}/findings` | `getDocumentFindings` | Findings reviewer |
| POST | `/api/applications/{application_id}/documents/{document_version_id}/approval` | `approveDocumentVersion` | Approve/reject per versi |
| GET | `/api/applications/{application_id}/documents/{document_version_id}/pdf` | `previewDocumentPdf` | Preview PDF non-final |

### 2.7 Export dan unduhan

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/applications/{application_id}/exports` | `listExports` | Riwayat ekspor |
| POST | `/api/applications/{application_id}/exports` | `createExport` | Ekspor versi approved (task) |
| GET | `/api/applications/{application_id}/exports/{export_id}/download` | `downloadExport` | Unduh file final |

### 2.8 Tasks

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/tasks/{task_id}` | `getTask` | Status, progress, partial success |
| POST | `/api/tasks/{task_id}/retry` | `retryTask` | Retry task atau sumber gagal |

### 2.9 Settings (`/settings`)

| Method | Path | Operation ID | Kegunaan |
|---|---|---|---|
| GET | `/api/settings` | `getSettings` | Gabungan pengaturan untuk halaman |
| GET | `/api/settings/preferences` | `getPreferences` | Preferensi pencarian |
| PUT | `/api/settings/preferences` | `updatePreferences` | Ganti preferensi |
| GET | `/api/settings/provider` | `getProviderSettings` | Provider, model, mapping role |
| PUT | `/api/settings/provider` | `updateProviderSettings` | Ubah provider/model/role |
| GET | `/api/settings/consent` | `getConsent` | Status consent + riwayat |
| POST | `/api/settings/consent` | `grantConsent` | Berikan consent |
| DELETE | `/api/settings/consent/{consent_id}` | `revokeConsent` | Tarik consent |
| GET | `/api/settings/sources` | `listSources` | Daftar source registry |
| POST | `/api/settings/sources` | `createSource` | Tambah sumber |
| GET | `/api/settings/sources/{source_id}` | `getSource` | Detail sumber |
| GET | `/api/settings/sources/health` | `getSourceHealth` | Kesehatan, jadwal, dan kuota semua sumber |
| PATCH | `/api/settings/sources/{source_id}` | `updateSource` | Ubah/nonaktifkan sumber |

Catatan inventaris:

- Tidak ada endpoint source registry untuk sumber sintetis `manual_url`. Sumber itu dikelola sistem dan tidak dapat dibuat, diubah, atau dinonaktifkan lewat `/api/settings/sources`. Lihat §3.4.
- Tidak ada endpoint hard delete sumber pada v1. Nonaktifkan dengan `enabled: false` agar job lama tetap tertelusur.
- Tidak ada endpoint override `ineligible`. D21 masih `OPEN`; default produk tidak punya override. Bila D21 dipertahankan, endpoint override ditambahkan lewat perubahan kontrak.
- Tidak ada endpoint cancel task. Lihat §4.3.
- Tidak ada endpoint auto-submit lamaran. Aksi Apply hanya membuka URL dari backend.

---

## 3. Payload Domain

Payload berikut adalah kontrak konsep. Bentuk final ada di draft OpenAPI; schema domain detail (Master CV/profil/job/eligibility/assessment/findings) adalah deliverable Phase 0 terpisah dan tidak diduplikasi di sini.

### 3.1 Master CV record (`PLAN.md` §4.1)

```json
{
  "master_cv_id": "mcv_...",
  "original_file": {
    "sha256": "...",
    "filename": "cv.pdf",
    "mime": "application/pdf",
    "size_bytes": 182341,
    "page_count": 2,
    "uploaded_at": "..."
  },
  "status": "uploaded | extracted | confirmed | superseded",
  "active_profile_version_id": "prf_...",
  "extraction_task_id": "tsk_...",
  "uploaded_at": "..."
}
```

`deduplicated` hanya ada pada response unggah (`MasterCvUploadResult`), bukan pada `GET /api/setup/master-cv`.

Aturan kontrak:

- `stored_path` tidak diekspos. Frontend memakai `GET /api/setup/master-cv/file` untuk file asli.
- `filename` adalah nama asli yang disanitasi, bukan path.
- Unggah ulang file dengan `sha256` sama mengembalikan record yang sama (`200`, `deduplicated: true`). Master CV tidak pernah ditimpa.
- Unggah file berbeda membuat Master CV **baru** (`201`). Master CV sebelumnya menjadi `superseded`.

**Siklus hidup Master CV.**

| Dari | Ke | Pemicu | Efek |
|---|---|---|---|
| — | `uploaded` | `POST /api/setup/master-cv` (file baru) | Record baru; file immutable |
| `uploaded` | `extracted` | Task `profile_extraction` selesai | Profil `draft` tersedia |
| `extracted` | `confirmed` | Profil turunannya `confirmed` | Master CV menjadi sumber fakta aktif |
| `uploaded`, `extracted`, `confirmed` | `superseded` | Unggah Master CV berbeda | Master CV baru aktif; record lama tetap tersimpan |

Aturan tambahan:

- `superseded` terminal dan read-only. Tidak ada transisi balik ke `uploaded`/`extracted`/`confirmed`.
- Tidak ada hard delete Master CV di v1; purge mengikuti [`DATA-AND-PRIVACY.md`](DATA-AND-PRIVACY.md) §6.
- Transisi ilegal ditolak `409 conflict`.

**Efek penggantian Master CV.** Unggah Master CV baru tidak boleh membuat artefak lama terlihat current:

| Artefak | Perlakuan |
|---|---|
| Master CV lama | `superseded`, file dan record dipertahankan |
| Profil `confirmed` lama | Tetap `confirmed` dan tetap profil aktif sampai draft dari Master CV baru dikonfirmasi; tidak diedit |
| Profil `draft`/`in_review` dari Master CV lama | Tetap tersimpan, ditandai bukan sumber aktif; tidak dapat dikonfirmasi sebagai profil dari Master CV baru |
| Eligibility, fit assessment, dokumen | `status_outdated: true` / status `outdated` bila memakai profil lama |
| Approval dan export record | Dipertahankan sebagai riwayat; file final yang sudah tercatat tidak berubah |
| Task berjalan | Tidak dibatalkan; hasilnya memakai versi yang dicatat saat task dimulai |

Tidak ada analisis ulang, regenerate, atau ekspor otomatis setelah penggantian. Aksi ulang eksplisit.

### 3.2 Profil (`PLAN.md` §4.1)

Field utama: `schema_version`, `profile_id`, `profile_version_id`, `master_cv_id`, `derived_from_profile_version_id`, `version`, `status`, `personal`, `education`, `experience`, `skills`, `projects`, `certifications`, `languages`, `awards`, `work_authorization`, `work_preferences`, `evidence_index`, `conflicts`.

Aturan kontrak:

- Setiap fakta CV membawa `evidence` berisi `evidence_id`.
- `evidence_index` memetakan `evidence_id` ke `doc_id`, `locator`, `quote` (lihat §4.12).
- Deklarasi pengguna memakai `source: user_declaration`.
- Frontend menampilkan evidence; tidak menghitung atau mengarang fakta.
- Koreksi memakai `expected_version`; mismatch menghasilkan `409 version_conflict`.
- Konfirmasi menolak versi yang masih punya konflik (`409 profile_conflicts_unresolved`).
- Konfirmasi profil bukan consent provider dan bukan approval dokumen.

**Siklus hidup versi profil.**

| Dari | Ke | Pemicu | Efek |
|---|---|---|---|
| — | `draft` | Ekstraksi selesai, atau koreksi atas versi `confirmed`/`superseded` | Versi baru; versi sumber tidak berubah |
| `draft` | `in_review` | Review pengguna dimulai | Koreksi masih boleh |
| `draft`/`in_review` | `confirmed` | `POST .../confirm` | Versi menjadi profil aktif |
| `confirmed` | `superseded` | Versi lain dikonfirmasi | Isi tetap; tidak lagi aktif |

**Mengoreksi profil yang sudah confirmed.**

1. `PATCH /api/setup/profiles/{profile_version_id}` pada versi `confirmed` membuat **draft baru** (`derived_from_profile_version_id` menunjuk versi sumber) dan menerapkan koreksi di draft itu. Response `201`. Versi confirmed tidak berubah.
2. Draft diedit dengan `PATCH` yang sama (response `200`), lalu direview.
3. Draft dikonfirmasi dengan `POST .../confirm`. Saat itu versi confirmed lama menjadi `superseded` dan pointer aktif berpindah.
4. Eligibility, fit, dan dokumen yang memakai versi lama ditandai `outdated`. Approval dan export record lama tetap sebagai riwayat.

Tidak ada rollback destruktif: `POST /api/setup/profile/rollback` hanya memindahkan pointer aktif ke versi `confirmed` yang pernah aktif. Rollback tidak menghapus versi, tidak mengubah isi, dan tidak membuat versi baru. Rollback ke versi yang tidak pernah `confirmed` ditolak `409 conflict`.

### 3.3 Preferensi pencarian (`PLAN.md` §4.2)

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

Aturan kontrak:

- `min_fit_score` default 0. Bila diubah, backend melaporkan `counts.hidden_by_min_fit_score`.
- `ranking.primary` hanya `fit_score_desc`. Tier tidak boleh menjadi primary.
- `tie_window` default 0, maksimum 20.
- `PUT` mengganti seluruh objek; tidak ada patch parsial preferensi.
- `seniority` dan `employment_types` memakai kosakata tertutup yang sama dengan metadata job: `intern`, `junior`, `mid`, `senior`, `lead`, `principal`, `unknown` dan `full_time`, `part_time`, `contract`, `internship`, `temporary`, `unknown`. Nilai sumber yang tidak dikenali dipetakan ke `unknown`, bukan diteruskan sebagai string bebas.

### 3.4 Source registry (`PLAN.md` §4.2)

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
  "enabled": true,
  "job_count": 12,
  "created_at": "...",
  "updated_at": "..."
}
```

`manual_url` valid sebagai tipe sumber (lihat sumber sintetis di bawah), tetapi bukan pilihan yang boleh dikirim klien saat membuat atau mengubah entri registry.

Aturan kontrak:

- Operasi UI: tambah, edit, nonaktifkan, ubah status verifikasi.
- `careers_url` divalidasi URL guard backend.
- Sumber baru selalu `unverified`. `enabled: true` pada `unverified` ditolak (`409 source_not_verified`).
- Sumber `broken` atau `restricted` tidak boleh diaktifkan.
- Tidak ada hard delete pada v1.
- `last_checked_at` diisi backend setelah percobaan fetch.
- `access_method` untuk entri yang dikelola pengguna hanya `ats_api` (board satu perusahaan). `aggregator` ditolak saat write (`400 validation_failed`, detail `access_method_unsupported`) sampai ada feed dengan ketentuan tertulis dan adapter; feed Himalayas dihapus 2026-10-23. `html` juga ditolak saat write karena tidak ada adapter yang dapat mengambilnya. `manual_url` bukan pilihan pengguna; nilai itu dipakai record sintetis. Baris lama bertipe `aggregator` atau `html` tetap dapat dibaca dan dinonaktifkan, tetapi tidak pernah di-fetch.
- `health_status` adalah turunan streak kegagalan, bukan penilaian terpisah: `unknown` belum ada percobaan, `healthy` percobaan terakhir sukses, `degraded` 1-2 gagal berurutan, `broken` 3 atau lebih gagal berurutan. `consecutive_failures` direset ke 0 setelah sukses.
- `next_run_at` adalah slot berikutnya. `null` berarti sumber langsung due. Sumber yang gagal mendapat backoff eksponensial (`interval × 2^(failure-1)`, maksimum faktor 8); `Retry-After` dari server dipakai sebagai lantai, bukan pengganti.
- `daily_request_quota` membatasi jumlah **HTTP request** per 24 jam, dihitung dari `SUM(discovery_run_source.request_count)` untuk baris yang `last_attempt_at` berada dalam 24 jam terakhir (bukan `source_fetch`, karena respons 304 dan kegagalan tidak menulis baris fetch). Setiap percobaan mencatat jumlah request yang benar-benar dipakai, jadi adapter berhalaman menghitung satu per halaman. `0` berarti tanpa batas. Sumber di-skip dengan `source_quota_exhausted` bila sisa kuota tidak cukup untuk seluruh kebutuhan run, sehingga tidak ada snapshot sebagian.
- `requests_last_24h` adalah jumlah HTTP request yang tercatat dalam 24 jam terakhir.
- `stale` bernilai true bila tidak ada fetch sukses selama 7 hari; ini peringatan, bukan perubahan status.
- `priority_order` menentukan urutan eksekusi scheduler; kecil lebih dulu. `fetch_interval_minutes` adalah jarak normal antar-run sukses.
- `GET /api/settings/sources/health` mengembalikan ringkasan yang sama untuk semua sumber dalam satu panggilan.

**Sumber sintetis `manual_url`.**

- `manual_url` adalah sumber yang dikelola sistem dengan identifier stabil `source_id: manual_url` dan tipe `manual_url`. Record ini disediakan backend, bukan dibuat pengguna.
- Job yang dibuat dari URL manual (`POST /api/applications` dengan `url`) mereferensikan `source_id: manual_url` dan `source_kind: manual_url`.
- Sumber sintetis tidak muncul di `GET /api/settings/sources`, tidak dapat diubah lewat `PATCH`, dan tidak dihitung sebagai entri registry.
- Pengguna **tidak perlu** mengonfigurasi sumber untuk memakai fallback URL manual. Discovery otomatis tetap memerlukan setidaknya satu entri registry `verified` dan `enabled`.
- `verification_status` sumber sintetis adalah `verified` untuk pemakaian manual oleh pengguna, karena URL divalidasi per request oleh URL guard; ini tidak menyatakan situs sumber sudah diuji untuk fetch otomatis.
- URL tetap divalidasi per request: HTTPS, host publik, tanpa kredensial, redirect tervalidasi, timeout 20 detik, maksimal 5 redirect, maksimal 5 MB. Kegagalan menghasilkan `400 url_rejected`.
- **Tempel teks (`text`).** `POST /api/applications` menerima `text` opsional bersama `url` untuk halaman yang tidak dapat diambil otomatis (403/429 atau shell JavaScript). Bila `text` diisi:
  - halaman **tidak** di-fetch dan `robots.txt` tidak diperiksa, karena tidak ada pengambilan otomatis;
  - `url` tetap wajib dan tetap divalidasi URL guard; URL menjadi `canonical_url` dan `apply_url` job. URL tidak pernah dikarang;
  - baris pertama teks menjadi judul; teks utuh menjadi `description_text` (dipotong sesuai batas normalisasi);
  - `text` maksimum 200.000 karakter; lebih dari itu ditolak `400 validation_failed`;
  - teks diperlakukan sebagai data tidak tepercaya, sama seperti isi halaman;
  - kegagalan parse menghasilkan `400 manual_page_unreadable`;
  - `source_fetch.raw_json` menyimpan teks tempel, `http_status`, `final_url`, dan `etag` bernilai `null`, dan `stats` run memuat `manual_text: 1` alih-alih `manual_url: 1`.

### 3.5 Eligibility result (`PLAN.md` §4.2)

```json
{
  "assessment_id": "ela_...",
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
      "evidence_refs": ["ev_..."],
      "reason": "Profil belum menyatakan status izin kerja untuk EU."
    }
  ],
  "confidence": "medium",
  "status_outdated": false,
  "computed_at": "..."
}
```

Aturan kontrak:

- `status` hanya `eligible`, `ineligible`, `needs_review`.
- Setiap check menyertakan kutipan lowongan dan referensi bukti/deklarasi profil.
- `needs_review` dan `ineligible` tidak membawa fit score.
- Status eligibility tidak dapat ditimpa lewat API. Perubahan hanya lewat analisis ulang eksplisit setelah profil atau versi deskripsi berubah.
- `status_outdated` dihitung backend.

### 3.6 Fit assessment

Field: `assessment_id`, `job_posting_version_id`, `profile_version_id`, `fit_score` (0–100), `verdict` (`strong`/`moderate`/`weak`), `confidence` (`low`/`medium`/`high`), `components[]` (`must_coverage`, `nice_coverage`, `experience_fit`), `gaps[]`, `status_outdated`, `computed_at`.

Aturan kontrak:

- Fit hanya dihitung untuk `eligible`. Untuk status lain, `GET .../fit` menghasilkan `409 fit_not_available`.
- Formula dan aturan ada di [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md).
- Setiap komponen dan gap dapat ditelusuri ke `requirement_id` dan `evidence_id`.
- Bobot dan ambang adalah rancangan awal; belum ada kalibrasi.

### 3.7 Findings reviewer (`PLAN.md` §7.3)

```json
{
  "document_version_id": "docv_...",
  "profile_version_id": "prf_...",
  "review_run_id": "rev_...",
  "cycle": 1,
  "verdict": "changes_required",
  "findings": [
    {
      "finding_id": "f1",
      "severity": "blocker",
      "category": "factuality",
      "location": {"doc": "cv", "section": "experience", "bullet_id": "exp_..._b2"},
      "quote": "Led a team of 12 engineers",
      "problem": "Jumlah tim tidak ada di evidence.",
      "evidence_refs": ["ev_..."],
      "suggested_fix": "Hapus angka; gunakan deskripsi yang didukung evidence.",
      "auto_fixable": false,
      "status": "open"
    }
  ],
  "reviewed_at": "..."
}
```

Aturan kontrak:

- Severity: `blocker`, `major`, `minor`, `nit`. Kriteria lulus: 0 `blocker`, 0 `major`.
- `verdict`: `pass`, `changes_required`, `unresolved`, `review_unavailable`.
- Findings tidak dihapus oleh approval. Approval pengguna tidak menghapus temuan.
- `cycle` maksimum 3 (review awal + 2 revisi).
- `profile_version_id` mencatat profil yang dipakai saat review; findings untuk versi profil lain tidak boleh ditampilkan sebagai current.

### 3.8 Export record (`PLAN.md` §4.3)

```json
{
  "export_id": "exp_...",
  "document_version_id": "docv_...",
  "profile_version_id": "prf_...",
  "document_hash": "...",
  "kind": "cv | cover_letter",
  "filename": "CV_<Candidate>_<Company>_<Position>.pdf",
  "status": "exported | tex_only | failed",
  "created_at": "...",
  "exported_at": null,
  "error": null,
  "download_url": null
}
```

Aturan kontrak:

- Ekspor hanya dari versi `approved` dengan `content_hash` yang cocok (`409 approval_hash_mismatch`, `409 export_not_ready`).
- `filename` dihitung backend. `filename` dari klien hanya mengganti nama, bukan isi atau approval; backend tetap menyanitasi dan dapat menambah suffix stabil.
- `profile_version_id` mencatat profil yang dipakai versi dokumen yang diekspor.
- `created_at` adalah waktu export record dibuat dan selalu terisi.
- `exported_at` **nullable**: terisi hanya bila `status: exported`, yaitu setelah PDF berhasil dibuat dan export record ditulis.
- `download_url` hanya terisi bila `status: exported`; `null` untuk `tex_only` dan `failed`.
- `error` memuat kode aman (misalnya `compile_failed`) untuk `tex_only`/`failed`, `null` untuk `exported`.
- Compile gagal menghasilkan export record `tex_only` (sumber LaTeX tersimpan, PDF tidak ada) atau `failed` (tidak ada artefak final); bukan `exported`. Kontrak tidak menetapkan mesin PDF; implementasi Phase 3 memakai Tectonic (D6 diputuskan 2026-10-21).
- `tex_only` adalah istilah produk yang sudah dipakai. Bila D6 memilih mesin non-LaTeX, nilai status baru ditambahkan lewat perubahan kontrak; nilai tidak diterima diam-diam.
- `ExportList` dan `DocumentList` dipaginasi dengan aturan §4.8.

---

## 4. Kontrak Perilaku

### 4.1 Status

Nilai status yang boleh muncul di API mengikuti [`PRODUCT.md`](PRODUCT.md) §5.7. Tiga konteks tidak boleh dicampur:

| Konteks | Field | Nilai |
|---|---|---|
| Proses/task | `Task.status` | `queued`, `processing`, `needs_review`, `completed`, `partial`, `failed` |
| Dokumen | `DocumentSummary.status` | `draft`, `in_review`, `approved`, `exported`, `outdated`, `failed` |
| Aplikasi | `ApplicationSummary.status` | `not_started`, `processing`, `needs_review`, `in_review`, `approved`, `exported`, `failed`, `outdated` |

`partial` hanya untuk task discovery: sebagian sumber berhasil, atau fetch berhasil tetapi analisis eligibility/fit gagal. `needs_review` pada task berarti task selesai tetapi menunggu tindakan manusia, bukan kegagalan. `outdated` bukan `failed`.

**Status task: superset internal dan pemetaan ke UI.** `Task.status` adalah status internal API dan superset dari status proses produk. `PRODUCT.md` §5.7 tidak diubah oleh pemetaan ini.

| `Task.status` API | Status proses/UI | Arti |
|---|---|---|
| `queued` | `Processing` | Task diterima, belum berjalan |
| `processing` | `Processing` | Task berjalan |
| `needs_review` | `Needs review` | Task berhenti menunggu tindakan manusia; bukan kegagalan |
| `completed` | `Completed` | Task selesai tanpa sisa pekerjaan |
| `partial` | `Completed` dengan penanda partial success | Discovery: sebagian sumber berhasil, atau fetch berhasil tetapi analisis eligibility/fit gagal; hasil sukses dipertahankan |
| `failed` | `Failed` | Task gagal; tidak ada hasil yang dapat dipakai |
| — (tidak ada task) | `Not started` | Turunan UI saat belum ada task; tidak dikirim sebagai `Task.status` |

Catatan pemetaan:

- `Completed` dan `partial success` adalah istilah UI. `PRODUCT.md` §5.7 tidak mencantumkan `Completed` sebagai status proses; ini ambiguitas yang dicatat, bukan keputusan baru. Backend tidak boleh mengirim `Completed` sebagai nilai `Task.status`.
- `partial` tidak boleh dipetakan ke `Failed`. Sumber yang gagal tetap terlihat per sumber.
- `Task.status` tidak boleh dipakai untuk status dokumen atau aplikasi. `ActivityEvent.status_context` memisahkan konteks lewat `kind`.
- Status aplikasi tetap proyeksi backend (§4.11), bukan hasil pemetaan langsung `Task.status`.

### 4.2 Identitas dan versi

- ID internal: UUIDv4 + timestamp; tampilan `job_7f3a2c91`.
- Setiap assessment dan dokumen menyertakan `profile_version_id` dan `job_posting_version_id`.
- Record riwayat dokumen (`DocumentSummary`, `DocumentVersion`), findings report, approval record, dan export record menyertakan `profile_version_id`.
- Approval dan ekspor menyertakan `document_version_id` + `content_hash`.
- Frontend wajib menampilkan versi yang dipakai, bukan hanya nilai agregat.
- Response daftar menyertakan `profile_version_id` yang dipakai untuk menghitung nilai pada halaman itu.

### 4.3 Tugas panjang

Fetch, parsing, generate, review, compile, dan ekspor berjalan sebagai task in-process. Tidak ada queue eksternal. Discovery di v1 berjalan sinkron di dalam request; lihat catatan di bawah.

**Eksekusi discovery di v1.** `POST /api/discovery/runs` menjalankan seluruh run secara sinkron di dalam request dan mengembalikan `202` setelah run selesai. Task dan status per sumber sudah final saat respons diterima. Konsekuensi yang harus dianggap bagian kontrak:

- Request dapat berjalan selama beberapa detik sampai batas `discovery.max_run_seconds`; klien tidak boleh memakai timeout lebih pendek dari batas itu.
- Sumber yang belum selesai saat batas tercapai ditandai `failed` dengan `error.code: run_timeout` dan `retryable: true`.
- Tidak ada progress bertahap selama run. `GET /api/tasks/{task_id}` tetap tersedia untuk membaca hasil akhir, retry, dan audit.
- Bila koneksi klien putus, run tetap diselesaikan oleh server karena pekerjaan tidak dibatalkan oleh disconnect.
- `GET /api/tasks/{task_id}` tidak boleh diasumsikan menunjukkan `processing` untuk discovery; nilai yang terlihat biasanya sudah final.

Pemindahan discovery ke worker thread adalah perubahan kontrak terpisah dan belum dilakukan.

**Membuat task.** Setiap aksi panjang mengembalikan `202` dengan `{ task_id, type, status }`. `type` hanya `profile_extraction`, `discovery`, `analysis`, `document_generation`, `review`, `export`.

**Membaca status.** `GET /api/tasks/{task_id}` mengembalikan:

```json
{
  "task_id": "tsk_...",
  "type": "discovery",
  "status": "partial",
  "application_id": null,
  "progress": {
    "current_stage": "eligibility",
    "completed_units": 7,
    "total_units": 10,
    "percent": 70,
    "stages": [
      {"name": "fetch", "status": "completed", "started_at": "...", "finished_at": "..."},
      {"name": "eligibility", "status": "processing", "started_at": "...", "finished_at": null}
    ]
  },
  "sources": [
    {
      "source_id": "src_...",
      "company": "...",
      "status": "failed",
      "fetched_count": 0,
      "accepted_count": 0,
      "duplicate_count": 0,
      "retry_count": 1,
      "stats": {"skipped": 0, "invalid": 0, "truncated": 0, "stale": 0},
      "close_skipped": null,
      "last_attempt_at": "...",
      "error": {
        "code": "source_unavailable",
        "message": "Sumber menolak akses otomatis.",
        "stage": "fetch",
        "retryable": false,
        "run_id": "run_...",
        "request_id": "...",
        "details": []
      }
    }
  ],
  "retry": {"retryable": true, "attempt": 1, "max_attempts": 3, "retry_after_seconds": null, "retried_from_task_id": null},
  "result": null,
  "error": null,
  "created_at": "...",
  "updated_at": "...",
  "finished_at": null
}
```

Aturan progress:

- `percent` hanya diisi bila `total_units` diketahui. Frontend tidak menghitung persentase sendiri dan tidak menampilkan persentase palsu.
- `stages` mencerminkan tahap pipeline yang benar-benar berjalan.
- Polling dengan interval minimum 1 detik; tidak ada backoff wajib di klien selain menghormati `Retry-After`. `Retry-After` boleh disertakan pada `200` task yang masih berjalan.
- Tidak ada streaming (SSE/WebSocket) di v1. Kontrak tidak menyediakan endpoint progress lain.

**Retry.** `POST /api/tasks/{task_id}/retry`:

- `scope` default untuk task `discovery` adalah `failed_sources`: hanya sumber berstatus `failed` atau `partial` yang retryable yang diulang; hasil sumber yang berhasil dipertahankan.
- `scope: all` mengulang seluruh task dan harus diminta eksplisit.
- `scope: failed_sources` hanya berlaku untuk task `discovery`.
- `scope: failed_sources` untuk tipe task lain ditolak `400 validation_failed` dengan `details[].code: retry_scope_unsupported`. Backend tidak diam-diam memperlakukan scope itu sebagai `all`.
- Retry membuat `task_id` baru dan menaikkan `attempt`. Task lama tetap dapat dibaca.
- Retry ditolak untuk task yang belum selesai (`409 task_not_finished`) atau tidak `retryable` (`409 task_not_retryable`).
- Maksimum 3 attempt untuk error transien. Error validasi, consent, gate, dan URL tidak di-retry.
- Backoff mengikuti `retry_after_seconds` bila ada; bila tidak, exponential backoff dengan batas atas yang sama untuk semua task.

**Cancel.** Tidak ada endpoint cancel di v1. Task berjalan sampai selesai atau `failed`. Asumsi satu pengguna, satu proses aplikasi.

**Partial success per sumber.** Status per sumber: `queued`, `processing`, `completed`, `partial`, `failed`, `skipped`. Aturan agregasi:

| Kondisi | `Task.status` |
|---|---|
| Semua sumber `completed`/`skipped` | `completed` |
| Minimal 1 sumber berhasil dan minimal 1 `failed`/`partial` | `partial` |
| Semua sumber `failed` | `failed` |
| Sumber gagal karena akses (403/429/CAPTCHA/login) | `failed`, `retryable: false`, tanpa bypass |
| Sumber gagal karena error jaringan/timeout | `failed`, `retryable: true` |

Hasil sukses tidak dihapus saat sumber lain gagal. `error` pada `SourceProgress` aman: tanpa konten halaman, tanpa URL query, tanpa path.

**Assessment setelah fetch.** Discovery menjalankan assessment dan ranking setelah fetch. Bila fetch berhasil tetapi assessment gagal:

- `DiscoveryRun.status` dan `Task.status` menjadi `partial`.
- `DiscoveryRun.error` dan `Task.error` memuat `code: assessment_failed`, `stage: eligibility`, `retryable: false`.
- Job hasil fetch tetap tersimpan; `counts` assessment berisi 0 karena tidak ada yang dihitung.
- Sumber tetap berstatus `completed`; kegagalan ini bukan kegagalan sumber.
- Retry sumber tidak memperbaiki assessment; jalankan discovery lagi setelah penyebabnya hilang.

### 4.4 Error

Envelope tunggal:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "Field 'url' bukan URL HTTPS yang diizinkan.",
    "stage": "validation",
    "retryable": false,
    "run_id": null,
    "request_id": "req_...",
    "details": [
      {"field": "url", "code": "url_scheme_not_https", "message": "Skema harus https."}
    ]
  }
}
```

Aturan:

- `code` stabil dan tertutup; nilai baru hanya ditambahkan lewat perubahan kontrak.
- `message` aman untuk ditampilkan; maksimum 500 karakter.
- `stage` menyebut komponen asal (`upload`, `fetch`, `eligibility`, `compile`, dan seterusnya).
- `retryable` menentukan apakah UI menawarkan retry.
- `run_id` dan `request_id` adalah referensi korelasi, bukan isi log.
- Dilarang: stack trace, prompt, respons model, isi dokumen, path filesystem, API key, PII.
- `details` maksimum 50 item dan hanya memuat nama field request, bukan path internal.

Kode error dan pemetaan HTTP:

| Kode | HTTP | `retryable` default | Arti |
|---|---|---|---|
| `validation_failed` | 400 | false | Schema/enum/rentang/field gagal |
| `not_found` | 404 | false | Resource tidak ada atau sudah dipurge |
| `csrf_invalid` | 403 | false | Token CSRF tidak ada/tidak cocok |
| `conflict` | 409 | false | Konflik state umum |
| `version_conflict` | 409 | false | `expected_version`/base hash tidak cocok |
| `idempotency_conflict` | 409 | false | `Idempotency-Key` sama, body berbeda |
| `task_already_running` | 409 | false | Task aktif lain untuk `application_id` yang sama; response memuat `active_task_id` |
| `task_not_retryable` | 409 | false | Task tidak boleh di-retry |
| `task_not_finished` | 409 | false | Retry saat task masih berjalan |
| `profile_not_confirmed` | 409 | false | Gate discovery/analisis belum terpenuhi |
| `profile_conflicts_unresolved` | 409 | false | Konfirmasi profil ditolak |
| `profile_version_mismatch` | 409 | false | Versi profil tidak sama dengan yang diminta |
| `eligibility_not_eligible` | 409 | false | Dokumen/fit diminta untuk `ineligible` |
| `eligibility_needs_review` | 409 | false | Dokumen diminta untuk `needs_review` |
| `assessment_failed` | — | false | Analisis eligibility/fit gagal setelah fetch; dilaporkan sebagai error run/task, bukan response HTTP |
| `fit_not_available` | 409 | false | Fit belum/tidak dihitung |
| `document_not_approved` | 409 | false | Ekspor versi belum approved |
| `approval_hash_mismatch` | 409 | false | Hash tidak cocok dengan versi |
| `approval_superseded` | 409 | false | Approval lama tidak berlaku untuk versi baru |
| `export_not_ready` | 409 | false | Export record belum siap |
| `pdf_not_available` | 409 | false | PDF belum dikompilasi |
| `review_unavailable` | 503 | true | Layanan reviewer tidak tersedia; tidak ada approval dicatat |
| `review_not_completed` | 409 | false | Gate approval: review belum selesai atau verdict belum final |
| `compile_failed` | 500 | true | Compile gagal setelah retry |
| `toolchain_unavailable` | 503 | false | Mesin PDF belum tersedia atau tidak dapat dipakai (D6 diputuskan 2026-10-21: Tectonic) |
| `provider_not_configured` | 409 | false | Provider belum dikonfigurasi (D1) |
| `provider_unavailable` | 503 | true | Provider gagal sementara; di dalam task dilaporkan sebagai error task dengan kode yang sama |
| `provider_rate_limited` | — | true | Rate limit provider; dilaporkan sebagai error task, bukan response HTTP |
| `consent_required` | 409 | false | Consent cloud belum diberikan |
| `url_rejected` | 400 | false | URL gagal URL guard |
| `source_not_verified` | 409 | false | Sumber belum diverifikasi |
| `source_restricted` | 409 | false | Sumber dibatasi ToS/akses |
| `source_unavailable` | 503 | true | Sumber gagal diakses |
| `source_unsupported` | — | false | Jenis sumber belum punya adapter; dilaporkan sebagai status `skipped` per sumber |
| `source_error` | — | true | Sumber gagal diproses di luar kategori lain; dilaporkan sebagai status `failed` per sumber |
| `source_parse_failed` | — | false | Payload sumber tidak dapat diparse; dilaporkan sebagai status `failed` per sumber |
| `response_too_large` | — | false | Respons sumber melebihi 5 MB |
| `run_timeout` | — | true | Batas durasi run discovery tercapai |
| `stale_run` | — | false | Task discovery basi dipulihkan saat run baru dimulai |
| `no_enabled_sources` | 409 | false | Tidak ada sumber `verified` dan `enabled` untuk dijalankan |
| `retry_scope_unsupported` | 400 | false | `scope` retry tidak berlaku untuk jenis task tersebut |
| `ats_unavailable` | 400 | false | Detail `validation_failed`: ATS tidak punya adapter |
| `ats_host_mismatch` | 400 | false | Detail `validation_failed`: host `careers_url` tidak cocok dengan ATS |
| `robots_disallowed` | 400 | false | `robots.txt` melarang pengambilan halaman URL manual |
| `manual_page_unreadable` | 400 | false | Halaman URL manual tidak memuat judul/deskripsi yang dapat dibaca, termasuk halaman yang dirender JavaScript |
| `source_quota_exhausted` | — | false | Kuota request harian sumber habis; dilaporkan sebagai status `skipped` per sumber |
| `empty_snapshot` | — | false | Snapshot tidak memuat record; penutupan lowongan dilewati |
| `all_records_invalid` | — | false | Semua record gagal dinormalisasi; penutupan lowongan dilewati |
| `payload_truncated` | — | false | Payload sumber terindikasi terpotong; penutupan lowongan dilewati |
| `invalid_ratio_high` | — | false | Rasio record invalid melebihi ambang; penutupan lowongan dilewati |
| `partial_snapshot` | — | false | Payload hanya sebagian dari board (adapter berpaginasi); penutupan lowongan dilewati |
| `access_method_unsupported` | 400 | false | Detail `validation_failed`: `access_method` tidak punya adapter fetch |
| `duplicate_source` | 409 | false | Sumber sudah terdaftar |
| `unsupported_media_type` | 415 | false | MIME/ekstensi tidak didukung |
| `payload_too_large` | 413 | false | Melebihi batas ukuran: JSON > 1 MiB atau file > 20 MB |
| `internal_error` | 500 | true | Error tak terduga tanpa detail sensitif |

Tidak ada rate limiting lokal pada API v1 dan tidak ada response HTTP `429` pada v1. Kode `rate_limited` dihapus dari kontrak. Rate limit provider muncul sebagai error task `provider_rate_limited` (`retryable: true`), bukan status HTTP, karena panggilan provider berjalan di dalam background task. Bila kelak ada rate limiting lokal atau `429` sinkron, kode dan endpoint yang menerapkannya harus dideklarasikan lewat perubahan kontrak.

### 4.5 CSRF dan session

- `GET /api/session` menetapkan cookie lewat header `Set-Cookie` (dua nilai pada satu response):
  - `gawe_session`: HttpOnly, `SameSite=Strict`, `Path=/`, `Secure` tidak dipakai karena HTTP localhost.
  - `gawe_csrf`: non-HttpOnly (dibaca API client), `SameSite=Strict`, `Path=/`.
- Response memuat `csrf_token`, `csrf_header` (`X-CSRF-Token`), `session_id`, dan `expires_at`.
- Setiap request `POST`, `PUT`, `PATCH`, `DELETE` wajib menyertakan `X-CSRF-Token` yang sama dengan cookie `gawe_csrf` dan terikat ke session.
- Token tidak valid atau tidak ada → `403 csrf_invalid`; tidak ada efek samping.
- `GET`, `HEAD`, `OPTIONS` tidak memerlukan token.
- Token dirotasi saat session kedaluwarsa atau proses aplikasi restart. Frontend mengambil ulang lewat `GET /api/session` dan mencoba ulang satu kali.
- API client menyertakan token otomatis. Komponen UI tidak mengelola token.
- Tidak ada CORS terbuka. Origin diperiksa sebagai pertahanan tambahan; penolakan tetap memakai `403 csrf_invalid`.
- Aturan Origin (selaras [`SECURITY.md`](SECURITY.md) §5):
  - Request mutasi wajib membawa `X-CSRF-Token` valid. Origin check tidak menggantikan token.
  - Bila header `Origin` dikirim, nilainya harus sama dengan origin API (`http://127.0.0.1:<port>` atau `http://localhost:<port>` pada port runtime) atau origin dev server Vite (`http://127.0.0.1:5173`, `http://localhost:5173`) saat proxy dev dipakai. Origin lain ditolak `403 csrf_invalid` tanpa efek samping.
  - Bila `Origin` tidak dikirim (klien non-browser), request tetap wajib membawa token CSRF. Origin yang tidak ada tidak melewati pemeriksaan token.
  - `Sec-Fetch-Site: cross-site` ditolak untuk request mutasi, termasuk bila token ada.
  - Proxy Vite hanya meneruskan ke `127.0.0.1:<port>`; proxy tidak membuka CORS dan tidak melonggarkan aturan Origin di backend.
- CSRF bukan pengganti bind `127.0.0.1` dan bukan autentikasi (D20 `OPEN`, default tanpa auth).

### 4.6 Validasi request

- Schema Pydantic untuk setiap request.
- Validasi enum, rentang, panjang, dan field wajib.
- `additionalProperties: false` pada objek request yang tidak boleh diperluas.
- Validasi URL memakai URL guard backend: HTTPS, host publik, tanpa kredensial, redirect divalidasi, timeout 20 detik, maksimal 5 redirect, maksimal 5 MB.
- Jangan mempercayai nilai otoritatif yang dikirim frontend (fit score, eligibility, ranking, approval, status, nama file final). Field tersebut tidak ada di schema request, atau diabaikan dengan `400 validation_failed`.
- Validasi file unggah: ekstensi, MIME, magic bytes, ukuran ≤ 20 MB, PDF ≤ 50 halaman, PDF terenkripsi ditolak, cek zip bomb DOCX. Gagal validasi tidak menulis sebagian.

### 4.7 Idempotensi dan konkurensi

Asumsi produk: satu pengguna, satu proses aplikasi pada satu waktu.

**Idempotensi alami.**

| Aksi | Perilaku duplikat |
|---|---|
| Unggah Master CV | `sha256` sama → `200`, `deduplicated: true`, tanpa versi baru |
| Buat application dari `job_id` | Workspace sudah ada → `200`, `deduplicated: true` |
| Approve versi + hash + keputusan sama | `200` + `Idempotency-Replayed: true`, record approval yang sudah ada |
| Ekspor versi + hash + nama sama | Task memakai artefak yang ada; tidak menimpa file final |
| Konfirmasi profil yang sudah aktif | `200`, idempoten |

**`Idempotency-Key`.** Opsional pada semua `POST` mutasi, termasuk `confirmProfileVersion` dan `rollbackProfile`.

- Key sama + body identik dalam 24 jam → response pertama diputar ulang dengan header `Idempotency-Replayed: true`.
- Key sama + body berbeda → `409 idempotency_conflict`.
- Key disimpan hanya untuk mutasi, bukan untuk `GET`.
- Record replay 24 jam adalah **cache teknis**. Ini bukan retensi data pengguna, bukan kebijakan D10, dan tidak boleh ditampilkan sebagai kebijakan retensi. D10 tetap `OPEN`.

**Konkurensi.**

Model konkurensi: task yang berkonflik diserialisasi **per `application_id`**, bukan satu task per tipe.

- Satu run discovery aktif pada satu waktu (discovery tidak terikat `application_id`). Run kedua → `409 task_already_running` + `active_task_id`; frontend menampilkan progress task aktif.
- Untuk satu `application_id`, hanya satu task aktif pada satu waktu, tanpa memandang tipe (`analysis`, `document_generation`, `review`, `export`). Task kedua yang berkonflik → `409 task_already_running` dengan `active_task_id`.
- Task yang tidak berkonflik secara data tetap boleh berjalan: misalnya task pada `application_id` berbeda, atau `profile_extraction` yang tidak menulis ke workspace aplikasi.
- `409 task_already_running` tidak membuat task baru dan tidak mengubah state. Body error memuat `active_task_id`.
- Pemulihan setelah reload: UI membaca `active_task_id` dari `GET /api/applications/{application_id}` atau `GET /api/overview`, lalu polling `GET /api/tasks/{task_id}`. UI tidak menyimpan state task sendiri dan tidak menebak status dari tombol yang dinonaktifkan.
- Dua `PATCH` profil dengan `expected_version` sama: yang kedua → `409 version_conflict`.
- Dua approval untuk versi + hash + keputusan sama: idempoten, `200` + `Idempotency-Replayed: true`. Keputusan berbeda mencatat record baru (`201`).
- Frontend tidak boleh mengasumsikan request selalu idempoten. UI menonaktifkan aksi selama request berjalan dan menampilkan task aktif.

### 4.8 Pagination, filter, dan sort

Pagination berbasis cursor untuk semua daftar, termasuk `DocumentList` (`GET /api/applications/{id}/documents`), `ExportList` (`GET /api/applications/{id}/exports`), `ProfileList`, `DiscoveryRunList`, `SourceList`, `ApplicationList`, `MatchList`, dan `ActivityList`:

- Query: `limit` (1–200, default 50), `cursor` (opaque).
- Response: `page: { limit, next_cursor, has_more }`.
- `next_cursor` `null` bila tidak ada halaman berikut.
- Cursor tidak valid → `400 validation_failed` dengan `details[].field = "cursor"`.
- Urutan harus stabil. Untuk `/api/matches` dengan `sort=ranking`, urutan mengikuti ranking run tersimpan; cursor memakai kunci ranking + `job_id`.
- Cursor adalah kunci keyset, bukan offset. Isinya: versi cursor, `sort`, `ranking_run_id` (bila ada), kunci urut, dan `job_id` terakhir. Request berikutnya mengembalikan item yang kuncinya lebih besar dari kunci cursor.
- Cursor yang dikirim dengan `sort` berbeda, atau dengan `ranking_run_id` yang berbeda dari ranking run terbaru, ditolak `400 validation_failed` (`details[].field = "cursor"`). Klien harus mulai lagi dari halaman pertama.
- Cursor yang dikirim tanpa `sort` dianggap milik `sort` default (`ranking`).

Filter dan sort Job Matches:

| Parameter | Nilai | Catatan |
|---|---|---|
| `eligibility` | `all`, `eligible`, `needs_review`, `ineligible` | Default `all` |
| `q` | teks ≤ 200 | Judul, perusahaan, lokasi |
| `tier` | `P1`–`P4`, `unclassified` | Filter tampilan |
| `source_id` | ID sumber | |
| `market` | `indonesia`, `global`, `unknown` | |
| `work_mode` | `onsite`, `remote`, `hybrid`, `unknown` | |
| `min_fit_score` | 0–100, default 0 | Filter tampilan; jumlah tersembunyi dilaporkan |
| `sort` | `ranking` (default), `fit_score_desc`, `posted_at_desc`, `priority_tier` | Selain `ranking` adalah sort tampilan dan diberi label |

Aturan:

- Filter/sort tidak mengubah skor, eligibility, atau ranking tersimpan.
- `priority_tier` bukan default dan harus diberi label saat dipakai.
- `needs_review` dan `ineligible` ditampilkan terpisah; keduanya tidak membawa fit score.
- Response `ranking` memuat `primary`, `tie_breaker`, `tie_window`, dan `ranking_run_id` agar UI menampilkan aturan yang dipakai.

**Koreksi tier pengguna (`PATCH /api/matches/{job_id}/tier`).**

- Body: `tier` (`P1`–`P4`, `unclassified`, atau `null` untuk menghapus koreksi) dan `reason` (teks ≤ 1000, wajib saat `tier` diisi).
- Koreksi disimpan pada job, bukan pada ranking run. Ranking run yang sudah tersimpan tidak berubah.
- Koreksi dipakai sebagai tie-breaker pada ranking berikutnya; `fit_score` dan eligibility tidak berubah.
- `tier` tidak dikenal atau `reason` kosong saat `tier` diisi → `400 validation_failed`.
- `job_id` tidak dikenal → `404 not_found`. Job yang belum dianalisis juga `404`.
- Response adalah `MatchItem` setelah koreksi, sehingga UI tidak perlu menebak nilai baru.
- Mengubah tier tidak mengubah urutan daftar sampai ranking dihitung ulang; UI harus menandai hal ini.

### 4.9 Batas ukuran respons dan streaming

- Response JSON tunggal ≤ 2 MiB. Daftar wajib dipaginasi.
- `JobDetail.description_text` ≤ 262144 byte UTF-8 (256 KiB). Batas diukur dalam byte, bukan karakter. Bila sumber lebih panjang, backend memotong pada batas byte dan mengisi `description_truncated: true`. Schema OpenAPI memakai `maxLength: 87381` (262144 / 3) sebagai batas karakter konservatif agar string UTF-8 tidak pernah melewati batas byte; `x-max-utf8-bytes: 262144` mencatat batas sebenarnya.
- Kutipan (`quote`) ≤ 2000 karakter (bukan byte).
- Request JSON ≤ 1 MiB; unggah file ≤ 20 MB. Pelanggaran menghasilkan `413 payload_too_large` dan dideklarasikan pada setiap operasi yang menerima body JSON atau unggah.
- Batas koleksi eksplisit agar batas response kredibel: `requirements` ≤ 500, `checks` ≤ 500, `findings` ≤ 500, `components` ≤ 10, `gaps` ≤ 200, `conflicts` ≤ 200, `evidence_refs` ≤ 100, `evidence_index` ≤ 5000 entri, `sources` ≤ 200, `stages` ≤ 50, `page.limit` ≤ 200.
- Tidak ada streaming JSON, SSE, atau WebSocket di v1. Progress dibaca lewat polling `GET /api/tasks/{task_id}`.
- Unduhan file (`Master CV`, PDF preview, file final) dikirim sebagai biner dengan `Content-Length` dan `Content-Disposition`; tidak dibungkus JSON dan tidak di-base64.
- Respons tidak memuat path filesystem, isi prompt, respons model, atau isi log.

### 4.10 Consent dan pengaturan provider

**Consent.**

- Consent cloud terpisah dari konfirmasi profil dan approval dokumen.
- `GET /api/settings/consent` mengembalikan `required`, `granted`, `current`, `required_scope`, `required_text`, `provider_changed_since_consent`, `model_changed_since_consent`, `history`, dan `history_truncated`.
- `required_text` adalah teks consent versi server: `text_version`, `text_sha256`, `display_text`, `issued_at`. UI menampilkan `display_text` sebelum pengguna memberi consent.
- `POST /api/settings/consent` mencatat `consent_record` (`consent_type`, `scope.data_classes`, `scope.provider_id`, `scope.model_roles`, `text_version`, `text_sha256`, waktu). `accepted` wajib `true`.
- `text_version` dan `text_sha256` **ditetapkan server** dari teks consent aktif saat request dicatat. Klien tidak mengirim `text_version`; nilai itu bukan bagian schema request dan ditolak `400 validation_failed` bila dikirim.
- Penyimpanan teks consent versioned (teks + hash + waktu berlaku) adalah tanggung jawab server dan dicatat sebagai data audit, selaras [`DATA-AND-PRIVACY.md`](DATA-AND-PRIVACY.md) §4.2.
- `DELETE /api/settings/consent/{consent_id}` menandai `revoked_at`; record tidak dihapus.
- Consent berlaku hanya bila `provider_id`, `data_classes`, dan model per role (`extract`, `classify`, `write`, `review`) sama dengan konfigurasi aktif saat data dikirim.
- Perubahan provider, perubahan model pada role mana pun, atau perubahan cakupan data menginvalidasi consent sebelumnya (`consent_renewal_required: true`, `model_changed_since_consent` atau `provider_changed_since_consent`). Consent baru wajib sebelum pengiriman data kandidat berikutnya.
- Riwayat consent dibatasi: `GET /api/settings/consent?history_limit=N` mengembalikan maksimum `history_limit` record terbaru (1–100, default 20). `history_truncated: true` berarti masih ada record lebih lama. Tidak ada endpoint riwayat tanpa batas.
- Tanpa consent, aksi yang mengirim data kandidat ke provider ditolak `409 consent_required` sebelum task dibuat.
- Consent tidak memberi izin auto-submit, tidak mengubah eligibility/approval, dan tidak mengklaim kebijakan retensi/training/region provider. D18 detail provider tetap `OPEN`.

**Provider dan role.**

- `GET /api/settings/provider` mengembalikan `provider_id`, `display_name`, `configured`, `base_url`, `roles` (`extract`, `classify`, `write`, `review`), `key_source`, `consent_renewal_required`, `updated_at`.
- `PUT /api/settings/provider` menerima provider/model/role dan `api_key_ref` (nama referensi keyring), bukan nilai secret. Perubahan model pada role mana pun memicu `consent_renewal_required`.
- API tidak pernah mengembalikan atau menerima nilai API key. `key_source` hanya `keyring`, `env`, atau `missing`.
- Tidak ada vendor atau model default. Tanpa konfigurasi, `configured: false` dan aksi LLM ditolak `409 provider_not_configured` (D1 sudah diputuskan: 9Router lewat `openai_compatible`; `base_url` dan model per role tetap konfigurasi).
- Satu provider aktif. Role boleh menunjuk model berbeda pada provider yang sama. Tidak ada fallback lintas provider otomatis.

**Retensi dan toolchain.**

- `GET /api/settings` menyertakan `retention.provisional: true` selama D10 belum disetujui. Durasi tidak boleh ditampilkan sebagai kebijakan final.
- Cache replay `Idempotency-Key` 24 jam bukan item retensi pengguna dan tidak termasuk tabel retensi. D10 tetap `OPEN`.
- `toolchain` melaporkan `pdf_engine`, `status`, dan `decision_status`. `pdf_engine` adalah konfigurasi runtime (string bebas atau `null`), bukan keputusan produk. D6 tetap `OPEN`; kontrak tidak menetapkan Tectonic atau mesin lain sebagai persyaratan.
- Ekspor PDF tidak dijanjikan bila mesin belum tersedia. Bila mesin PDF belum tersedia atau tidak dapat dipakai, `POST .../exports` dan preview PDF ditolak `503 toolchain_unavailable` (`retryable: false`) dan preview menghasilkan `409 pdf_not_available`.
- Ekspor yang gagal compile tetap mencatat export record `tex_only` atau `failed`; tidak ada klaim PDF berhasil.

### 4.11 Status dan transisi workflow melalui API

Aksi API dan transisi yang diizinkan:

| Aksi | Endpoint | Prasyarat | Efek status |
|---|---|---|---|
| Unggah Master CV | `POST /api/setup/master-cv` | File valid | Master CV baru `uploaded`; Master CV lama `superseded` |
| Ekstraksi | `POST /api/setup/master-cv/extractions` | Master CV ada, provider + consent siap | Task `profile_extraction`; profil `draft` |
| Koreksi (draft/in_review) | `PATCH /api/setup/profiles/{id}` | Status `draft`/`in_review` | Tetap `draft`/`in_review` |
| Koreksi (confirmed) | `PATCH /api/setup/profiles/{id}` | Status `confirmed`/`superseded` | Draft baru `derived_from_profile_version_id`; versi sumber tidak berubah |
| Konfirmasi | `POST /api/setup/profiles/{id}/confirm` | Tidak ada konflik terbuka | Profil `confirmed`, versi confirmed lama `superseded`; analisis/dokumen lama `outdated` |
| Rollback | `POST /api/setup/profile/rollback` | Target pernah `confirmed` | Pointer aktif berpindah; tanpa versi baru; tanpa hapus |
| Discovery | `POST /api/discovery/runs` | Profil `confirmed` | Task `discovery` |
| Analisis | `POST /api/applications/{id}/analysis` | Profil `confirmed` | Task `analysis`; hasil baru menggantikan assessment aktif |
| Generate | `POST /api/applications/{id}/documents` | Eligibility `eligible` | Task `document_generation`; versi baru `draft` |
| Review | `POST .../documents/{id}/review` | Versi ada | Task `review`; versi tetap `draft`/`in_review` |
| Review selesai (QA lulus) | — | Task `completed` | Versi `in_review` |
| Approve | `POST .../documents/{id}/approval` | Review selesai, hash cocok, data wajib lengkap, eligibility `eligible` | Versi `approved` |
| Reject / minta perubahan | `POST .../documents/{id}/approval` | Hash cocok | Versi tetap `in_review`; catatan tercatat |
| Buat application dari `job_id`/`url` | `POST /api/applications` | Profil `confirmed` | Workspace baru; task fetch/analisis; tanpa profil confirmed ditolak `409 profile_not_confirmed` |
| Edit | `POST .../documents/{id}/revisions` | Versi ada | Versi baru `draft`; versi lama tidak berubah |
| Regenerate | `POST .../documents/{id}/regenerate` | Eligibility `eligible` | Versi baru `draft` |
| Ekspor | `POST /api/applications/{id}/exports` | Versi `approved`, hash cocok | Task `export`; sukses → `exported` |
| Sumber berubah | — | Profil/job version baru | Assessment/dokumen terkait `outdated`; tanpa regenerate otomatis |

Aturan:

- `approved` hanya dari `in_review` dengan review selesai. `Ready for review` bukan `approved`.
- `exported` hanya setelah PDF berhasil dan export record ditulis. Compile gagal tidak menghasilkan `exported`.
- Versi baru setelah edit/regenerate tidak mewarisi approval. Approval lama tetap sebagai riwayat (`approval_superseded` bila dipakai untuk ekspor versi baru).
- `outdated` tidak memicu analisis ulang atau regenerasi otomatis. Aksi ulang eksplisit.
- `outdated` pada versi yang sudah `exported` tidak mengubah file final yang sudah tercatat.
- Status aplikasi adalah proyeksi backend dengan presedensi tetap: task aktif → `processing`; kegagalan tak terpulihkan → `failed`; eligibility `needs_review` atau reviewer tidak tersedia → `needs_review`; ada analisis/dokumen `outdated` → `outdated`; ada dokumen `in_review` → `in_review`; semua dokumen wajib `exported` → `exported`; minimal satu `approved` → `approved`; selain itu `not_started`. Frontend hanya menampilkan.
- Transisi ilegal ditolak `409`, bukan diterima lalu diperbaiki di UI.
- `createApplication` dan `rerunApplicationAnalysis` mensyaratkan profil `confirmed`; pelanggaran menghasilkan `409 profile_not_confirmed` tanpa membuat workspace atau task.
- **Ambiguitas `rejected` vs `changes_requested` (belum diselesaikan).** `PRODUCT.md` §5.4 dan `PLAN.md` §4.3 hanya menetapkan bahwa versi tidak berubah dan approval tidak diberikan. Tidak ada sumber produk yang membedakan efek kedua keputusan. Kontrak saat ini menerima keduanya dan memperlakukan efeknya sama: versi tetap `in_review`, catatan dicatat, tidak ada approval baru yang berlaku. Perbedaan efek (misalnya `rejected` menutup versi) **tidak dikarang** dan menunggu keputusan pengguna.

#### 4.11.1 Implementasi dokumen deterministik (milestone 3D)

Milestone ini mengimplementasikan versi, review, dan approval. LaTeX/PDF/ekspor ditambahkan pada gap-closing 2026-10-21 (lihat A4.11.2); D6 sudah diputuskan.

- Draft CV/cover letter dibangun deterministik dari `profile_version.content` + job. Tidak ada provider/model call; `provider`, `model`, dan `prompt_version` bernilai `null`.
- Hash versi adalah SHA-256 dari canonical JSON konten (`sort_keys`, separator rapat, UTF-8). Hash berubah bila konten berubah.
- Diff versi 1 membandingkan dokumen dengan Master CV (`selected`/`omitted`/`summarized`). Diff versi revisi/regenerate membandingkan dengan versi induk (`added`/`removed`/`changed`) dan mencatat `base_document_version_id`.
- Review deterministik memeriksa: data wajib ada, setiap klaim membawa minimal satu `evidence_id`, dan setiap `evidence_id` ada di `evidence_index` profil. Verdict `pass` bila tidak ada `blocker`/`major`; selain itu `changes_required`. Reviewer LLM (D9) belum dijalankan, sehingga verdict `review_unavailable` tidak dihasilkan.
- Approval ditolak `409` bila: hash tidak cocok (`approval_hash_mismatch`), review belum selesai (`review_not_completed`), eligibility bukan `eligible` (`eligibility_needs_review`/`eligibility_not_eligible`), eligibility `status_outdated` (`conflict` + `assessment_outdated`), atau data wajib belum lengkap (`conflict` dengan `details[].code` = `missing_required_field`/`missing_required_section`).
- Generate dan regenerate juga menolak eligibility `status_outdated`. Review ulang versi yang sudah `approved` ditolak `409 conflict` + `version_already_approved`; buat versi baru.
- Data wajib minimum: `header.full_name` dan minimal satu dari `experience`, `projects`, `education`.
- Approval yang diulang dengan versi, hash, dan keputusan yang sama mengembalikan record yang sama (`200`, header `Idempotency-Replayed: true`). Keputusan berbeda menambah record baru (append-only) selama versi belum `approved`; versi yang sudah `approved` menolak keputusan lain dan review ulang dengan `409 conflict` + `version_already_approved`.
- Approval menghitung ulang hash dari `content_json`; hash tersimpan yang tidak cocok dengan konten ditolak `approval_hash_mismatch`.
- Revisi menolak perubahan `kind`, `schema_version`, `target`, `missing`, `language`, dan semua `evidence_ids`; tipe struktur dasar (`header`, `target`, `summary`, `paragraphs`, list section) divalidasi sebelum versi baru dibuat.
- Catatan revisi disimpan di `diff.note`; catatan per edit disimpan di `diff.edit_notes`.
- Approval tidak menghapus findings. Findings tetap menempel pada `document_version_id` dan `profile_version_id` saat review.
- Konten tidak boleh disetujui atau diekspor bila data wajib belum lengkap.

#### 4.11.2 Implementasi PDF dan ekspor (gap-closing 2026-10-21)

D6 diputuskan: Tectonic 0.17.0 menghasilkan PDF dari LaTeX yang dibangun backend.

- `GET .../documents/{document_version_id}/pdf` adalah preview non-final. Tidak membuat export record, tidak mengubah status approval/ekspor. Respons `application/pdf` dengan `Content-Disposition: inline`.
- `POST .../exports` menerima `kind` + `document_version_id` + `content_hash` (+ `filename` opsional) dan mengembalikan `202` `TaskCreated` bertipe `export`. Nama file dihitung backend; `filename` hanya mengganti nama.
- Gate sebelum task dibuat: `404` versi asing, `400 validation_failed` bila `kind` tidak cocok, `409 approval_hash_mismatch` bila hash tidak cocok, `409 export_not_ready` bila versi belum `approved`, `409 task_already_running` + `active_task_id` bila ada task aktif, dan `503 toolchain_unavailable` bila mesin PDF tidak tersedia. Karena `503` terjadi sebelum task, tidak ada export record setengah jadi.
- `qa` memeriksa batas halaman (CV maks 2, cover letter maks 1) dan PDF yang dapat dibaca. `qa` gagal menghasilkan record `failed` dengan `error.code` dari masalah pertama; tidak pernah `exported`.
- Kompilasi gagal saat runtime (timeout, error LaTeX) menghasilkan `tex_only` dengan sumber LaTeX tersimpan dan `download_url: null`.
- `GET .../exports/{export_id}/download` hanya melayani record `exported`; selain itu `409 export_not_ready`.
- Hasil nyata 2026-10-21: CV 1 halaman (16.3 KB), cover letter 1 halaman (11.8 KB) untuk dua lowongan global nyata.

### 4.12 Representasi evidence dan kutipan di UI

- `evidence_index` adalah map `evidence_id` → objek evidence:

```json
{
  "ev_...": {
    "evidence_id": "ev_...",
    "source": "cv | user_declaration",
    "doc_id": "doc_...",
    "locator": {"page": 1, "section": "experience", "block_id": "exp_2_b1", "char_start": 812, "char_end": 940},
    "quote": "Led migration of billing service to PostgreSQL.",
    "declared_at": null
  }
}
```

- `source: cv` menampilkan label sumber dan locator yang tersedia (`page`, `section`).
- `source: user_declaration` menampilkan label "Deklarasi pengguna" dan `declared_at`.
- `quote` adalah teks polos. Frontend merender sebagai teks, bukan HTML; tidak ada `dangerouslySetInnerHTML`.
- `locator` tidak memuat path filesystem. `doc_id` adalah ID internal, bukan path.
- Kutipan yang tidak ditemukan di sumber asli tidak boleh ditampilkan sebagai evidence; validator backend menolak.
- Eligibility check, fit component/gap, findings, dan dokumen turunan memakai `evidence_id` yang sama. Frontend tidak membuat atau memetakan evidence sendiri.

### 4.13 Perilaku saat provider atau reviewer tidak tersedia

| Kondisi | Perilaku API |
|---|---|
| Provider belum dikonfigurasi (D1) | `409 provider_not_configured`, `retryable: false`; tidak ada task |
| Consent belum diberikan | `409 consent_required`, `retryable: false`; tidak ada task |
| Provider gagal sementara | Task `failed` dengan `provider_unavailable`, `retryable: true`; checkpoint disimpan; retry melanjutkan dari checkpoint |
| Provider rate limit | Task `failed` dengan error `provider_rate_limited`, `retryable: true`, `retry_after_seconds` di `RetryInfo` bila diketahui. Tidak ada response HTTP `429` pada API v1 |
| Provider gagal saat eligibility | Task `needs_review` dengan error `provider_unavailable`; assessment tidak ditulis; tidak menebak status |
| Reviewer gagal | Task `failed` dengan `review_unavailable`; dokumen tidak siap; approval ditolak `503 review_unavailable` (`retryable: true`) |
| Review belum selesai | Approval ditolak `409 review_not_completed` (`retryable: false`); ini gate, bukan kegagalan layanan |
| Reviewer gagal setelah 2 siklus revisi | `verdict: unresolved`; sisa temuan dilaporkan; approval tetap keputusan pengguna dengan temuan terlihat |
| Compile gagal | Export record `tex_only` atau `failed`; dokumen tidak `exported`; error `compile_failed` `retryable: true` |
| Mesin PDF belum tersedia | Ekspor ditolak `503 toolchain_unavailable`, `retryable: false`; preview PDF `409 pdf_not_available`. Tidak ada mesin PDF yang diwajibkan kontrak |

Tidak ada fallback lintas provider otomatis. Tidak ada klaim bahwa dokumen siap saat reviewer tidak tersedia.

---

## 5. Batas Tanggung Jawab

| Nilai | Dihitung di | Frontend |
|---|---|---|
| Eligibility | Backend | Tampilkan |
| Fit score dan komponen | Backend | Tampilkan |
| Ranking | Backend | Tampilkan urutan; filter/sort tampilan tidak mengubah skor |
| Recommendation | Backend | Tampilkan |
| Approval | Backend | Kirim aksi; tampilkan status |
| `Outdated` | Backend | Tampilkan |
| Status aplikasi | Backend (proyeksi) | Tampilkan |
| Nama file final | Backend | Tampilkan; pengguna boleh mengedit nama sebelum ekspor |
| `next_action` | Backend | Tampilkan |
| Persentase progress | Backend (bila `total_units` diketahui) | Tampilkan; jangan hitung sendiri |

---

## 6. Kontrak yang Wajib Ditutup (`OPEN` → status)

Daftar asal: item wajib Phase 0. Status di bawah berarti **tertutup dan disetujui pengguna 2026-10-19**.

| # | Item | Ditutup di | Status |
|---|---|---|---|
| 1 | Inventaris endpoint lengkap per halaman | §2.1–§2.9 | Tertutup |
| 2 | Skema request/response final (OpenAPI) | `../phase-00/contracts/openapi.yaml`; §3 | Tertutup. Schema domain detail adalah deliverable terpisah |
| 3 | Error envelope dan kode error | §4.4 | Tertutup |
| 4 | Pagination, filter, dan sort Job Matches | §4.8 | Tertutup |
| 5 | Skema task/progress/retry | §4.3 | Tertutup |
| 6 | Endpoint upload dan validasi file | §2.2, §4.6, §3.1 | Tertutup |
| 7 | Endpoint konfirmasi profil dan rollback versi | §2.2, §4.11, §3.2 | Tertutup |
| 8 | Endpoint consent dan settings provider | §2.9, §4.10 | Tertutup |
| 9 | Endpoint source registry CRUD | §2.9, §3.4 | Tertutup. Delete = nonaktifkan; hard delete tidak ada di v1 |
| 10 | Endpoint approval per versi dan ekspor/unduh | §2.6, §2.7, §3.8, §4.11 | Tertutup |
| 11 | Mekanisme CSRF (header, cookie, session) | §4.5 | Tertutup |
| 12 | Bentuk representasi evidence dan kutipan di UI | §4.12 | Tertutup |
| 13 | Batas ukuran respons dan streaming | §4.9 | Tertutup |
| 14 | Perilaku saat provider/reviewer tidak tersedia | §4.13, §4.4 | Tertutup |

Catatan: penutupan item 1–14 tidak mengubah keputusan produk. C4 ditutup setelah pengguna menyetujui kontrak ini pada 2026-10-19.

Amandemen kontrak (remediasi Phase 0) memperluas isi item berikut tanpa menambah item baru: §2.2 (idempotensi konfirmasi/rollback), §3.1 (siklus hidup dan penggantian Master CV), §3.2 (koreksi profil confirmed), §3.4 (sumber sintetis `manual_url`), §3.8 (export record), §4.1 (pemetaan status task), §4.3 (konkurensi per application), §4.5 (Origin), §4.8–§4.9 (pagination dan batas), §4.10 (consent versioned dan D6).

---

## 7. Verifikasi Kontrak

- OpenAPI dapat di-parse dan lolos lint struktural.
- Semua `$ref` resolve internal dan `operationId` unik.
- Setiap operasi mutasi mendeklarasikan CSRF/session dan `413` bila menerima body JSON.
- Setiap `POST` mutasi menerima `Idempotency-Key` opsional.
- OpenAPI dapat di-generate menjadi tipe TypeScript.
- Typecheck gagal bila kontrak berubah tanpa penyesuaian.
- Contract test untuk route group utama.
- Test CSRF: tanpa token, token salah, token valid.
- Test error tidak memuat PII/secret/path.
- Test frontend tidak mengirim nilai otoritatif yang bisa mengubah hasil.
- Test gate: `needs_review`/`ineligible` memblokir dokumen; ekspor non-approved ditolak; hash mismatch ditolak.
- Test idempotensi: unggah ganda, application ganda, approval ganda, `Idempotency-Key`.
- Test pagination: cursor invalid, halaman terakhir, urutan stabil.
- Test partial success discovery: satu sumber gagal, hasil lain tetap ada, retry hanya sumber gagal.

Verifikasi yang benar-benar dijalankan pada tugas ini dicatat di laporan tugas. Jangan mengklaim verifikasi yang tidak dijalankan.

Catatan warning lint: Redocly `operation-4xx-response` masih menyala untuk lima operasi baca `getSession`, `getOverview`, `getSettings`, `getPreferences`, dan `getProviderSettings`. Warning ini **dapat diterima**: operasi tersebut tidak memiliki input path/query yang dapat gagal validasi dan tidak punya kegagalan 4xx yang benar-benar ada di kontrak. Menambahkan respons 4xx palsu hanya akan menyembunyikan warning tanpa menambah kejadian nyata. `getSession` mengembalikan `500` bila state session gagal dibuat; `getOverview`/`getSettings`/`getPreferences`/`getProviderSettings` mengembalikan `500` untuk kegagalan baca. Bila kelak salah satu operasi memperoleh input yang dapat gagal validasi, respons 4xx harus ditambahkan.

---

## 8. Referensi PLAN.md

- §4.0 A0 Stack frontend (API JSON, tipe dari OpenAPI)
- §4.1 Master CV record dan profil
- §4.2 Preferensi, source registry, eligibility result
- §4.3 Approval, ekspor, bundle
- §6 Arsitektur komponen (HTTP API, API client + tipe)
- §7.3 Format findings
- §8 Rekomendasi stack
- §9 Data model
- §12 Mapping workflow ke API
- §13 Phase 0 (kontrak API)
