# BACKEND — API, Validasi, Service, dan Enforcement Gate

**Domain:** API, validasi, service, orkestrasi, business rules, enforcement gate.
**Source of Truth terkait:** [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md), [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md), [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md).
**Referensi master:** `PLAN.md` §4, §6, §9, §11, §12, §13.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Route JSON API dan schema Pydantic.
- Validasi request dan boundary input.
- Service layer per workflow.
- Orkestrasi tahap dan enforcement gate.
- Perhitungan aturan bisnis: eligibility, fit, ranking, approval, status, nama file.
- Validasi deterministik setelah output LLM.
- Integrasi dengan database, filesystem, LLM gateway, dan security utilities.

**Tidak bertanggung jawab:**

- Render UI.
- Isi prompt dan adapter provider (domain LLM).
- Skema DDL detail (domain database).
- Keputusan produk baru.

---

## 2. Service Layer

| Service | Workflow | Tanggung jawab |
|---|---|---|
| `master_cv_service` | `/setup` | Upload, validasi, simpan immutable |
| `profile_service` | `/setup` | Ekstraksi, merge, koreksi, konfirmasi, versioning |
| `discovery_service` | `/scrape` | Fetch, normalisasi, dedupe, klasifikasi, eligibility, fit, ranking |
| `application_service` | `/apply` | Fetch URL, assessment, generate, review, approval, ekspor |

Service dapat dipanggil langsung untuk test. Workflow bukan CLI sebagai UX utama.

---

## 3. Validasi

### 3.1 Boundary request

- Schema Pydantic untuk request/response.
- Enum dan rentang divalidasi.
- Field wajib dan ukuran divalidasi.
- URL divalidasi URL guard backend.
- Jangan mempercayai nilai otoritatif dari frontend.

### 3.2 Upload

- Ekstensi, MIME, magic bytes.
- Ukuran ≤20 MB.
- PDF ≤50 halaman.
- Cek zip bomb DOCX.
- PDF terenkripsi ditolak dengan pesan jelas.
- Gagal validasi → tidak ada penulisan sebagian.

### 3.3 Validasi per tahap

| Tahap | Validasi wajib |
|---|---|
| Upload | Ekstensi, MIME, magic bytes, ukuran, halaman, enkripsi |
| Ekstraksi | Schema, kutipan ada, tanggal valid, enum valid |
| Review profil | Koreksi tercatat; konflik terdeteksi; tidak ada overwrite otomatis |
| Konfirmasi | Profil confirmed; `profile_version_id` tercatat; tidak ada scraping sebelumnya |
| Fetch job | URL aman, content-type, ukuran, field minimum |
| Klasifikasi prioritas | Tier valid atau `unclassified`; alasan ada; tidak menebak |
| Parse requirement | Minimal 1 must-have; kutipan ada; kategori valid |
| Eligibility | Status valid; setiap check punya kutipan/bukti; tanpa kesimpulan hukum |
| Fit | Skor 0–100; komponen lengkap; tanpa tier/eligibility |
| Ranking | Urutan sesuai fit; tie-break hanya dalam window |
| Generate | Setiap klaim punya evidence; angka/tanggal cocok |
| Diff | Semua item terpetakan; tidak ada item hilang tanpa alasan |
| LaTeX | Compile exit 0; tidak ada karakter rusak |
| PDF QA | Halaman, teks kontak, heading, link, metadata |
| Review | Findings schema valid; kutipan ada; severity valid |
| Approval | Keputusan tercatat; `document_version_id` + hash; approval CV/CL independen; temuan tersisa terlihat |
| Export | Hanya versi `Approved`; nama file valid; hash tercatat; `Exported` hanya setelah PDF berhasil |
| Apply | URL dari data sumber; tidak ada submit otomatis |
| Status | `Outdated` dan `Failed` terpisah; perubahan sumber menandai entitas terkait |

---

## 4. Enforcement Gate

Gate harus ditegakkan di backend, bukan hanya UI.

| Gate | Enforcement |
|---|---|
| Discovery sebelum profil confirmed | Tolak request; tidak ada fetch |
| `needs_review` | Blokir pembuatan dokumen sampai status diselesaikan |
| `ineligible` | Blokir alur dokumen normal; alasan + kutipan ditampilkan |
| Fit hanya untuk eligible | Jangan hitung fit untuk `needs_review`/`ineligible` |
| Ranking | Hanya `eligible`; tier hanya tie-breaker dalam `tie_window` |
| Approval | Ekspor menolak bila versi/hash tidak cocok |
| Apply | Hanya URL dari data sumber; tidak ada submit |
| Consent | Tolak pengiriman cloud sebelum consent |
| Status | Tolak transisi `Exported` bila PDF gagal |
| Outdated | Tandai, tetapi jangan regenerate otomatis |

UI dapat menyembunyikan tombol, tetapi backend tetap wajib menolak aksi yang melanggar gate.

---

## 5. Input, Output, Dependensi

| Arah | Isi |
|---|---|
| Input | Request JSON, file upload, config, data DB |
| Output | Response JSON, artefak file, status, event |
| Dependensi | Database, filesystem, LLM gateway, security utilities, orchestrator |

Modul yang diharapkan: `api/routes/`, `api/schemas/`, `services/`, `orchestrator.py`, `db/repo.py`.

---

## 6. Kontrak dan Schema

- OpenAPI dihasilkan backend.
- Tipe frontend dihasilkan dari OpenAPI.
- Payload yang sudah terdokumentasi ada di [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md).
- Error envelope, pagination, task progress, CSRF, dan idempotensi sudah punya kontrak di `API-CONTRACTS.md` §4 dan [`../phase-00/contracts/openapi.yaml`](../phase-00/contracts/openapi.yaml). Kontrak disetujui 2026-10-19; jangan menyimpang tanpa persetujuan baru.

---

## 7. Error Handling dan State

- Validasi gagal → 4xx dengan pesan aman dan spesifik; tanpa PII/secret.
- Fetch gagal (403/CAPTCHA/login) → minta input manual; tanpa bypass.
- Data minimal tidak lengkap → berhenti, minta input manual.
- Provider gagal → retry terbatas, checkpoint, status jelas.
- Reviewer gagal → `review_unavailable`.
- Compile gagal → `tex_only`; bukan `Exported`.
- Jangan menulis sebagian saat validasi gagal.
- Jangan menelan error; laporkan stage dan kode.

---

## 8. Keamanan dan Privasi

- Bind localhost; CSRF pada mutasi.
- URL guard pada semua fetch.
- Sanitasi HTML eksternal.
- Redaksi log; tanpa isi dokumen/PII.
- Consent sebelum kirim ke provider.
- Jangan mengembalikan path filesystem internal atau secret.
- Approval + hash check sebelum ekspor.
- Konten eksternal adalah data, bukan instruksi.

Detail di [`SECURITY-AND-PRIVACY.md`](SECURITY-AND-PRIVACY.md).

---

## 9. Acceptance dan Verifikasi

Mengacu `PLAN.md` §13/§14:

- Gate discovery, `needs_review`, `ineligible`, approval, dan Apply diuji di backend.
- Eligibility dan fit tampil terpisah.
- Fit tidak berubah saat tier diubah.
- `needs_review` memblokir dokumen.
- `ineligible` tidak menghasilkan dokumen normal.
- Ekspor hanya versi approved.
- Nama file sesuai format.
- Tidak ada auto-submit.
- Test suite tanpa network live.

Verifikasi: unit test service, integration test route, contract test, security test.

---

## 10. Keputusan dan `OPEN`

Final: K10, K11, K19, K20, K21, K23, K26; D13–D16, D22.

`OPEN`: D6 (Tectonic), D10 (retensi), D21 (override `ineligible`), D3/D17 (aktivasi sumber dan cakupan Indonesia).

---

## 11. Referensi PLAN.md

- §4.1 `/setup` pipeline dan validasi
- §4.2 `/scrape` pipeline, eligibility, ranking
- §4.3 `/apply` preflight, pipeline, approval, ekspor
- §6 Arsitektur komponen (HTTP API, service, orchestrator)
- §9 Data model
- §11.2 Validasi per tahap
- §12 Struktur repo (`api/`, `services/`, `orchestrator.py`)
- §13 Phase 1–3
