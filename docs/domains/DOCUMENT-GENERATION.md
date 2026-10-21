# DOCUMENT-GENERATION — Tailoring, Approval, LaTeX, dan Ekspor

**Domain:** tailoring CV/cover letter, versi, review, approval berbasis versi dan hash, LaTeX, PDF, ekspor.
**Source of Truth terkait:** [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md) §5.4–5.6, [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) (D5, D6, D19, D21).
**Referensi master:** `PLAN.md` §4.3, §7, §9, §13 Phase 3, §14 kriteria 14–23.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Memilih bukti relevan dari profil confirmed.
- Menyusun CV turunan dan cover letter per lowongan.
- Integritas deterministik dan diff vs Master CV.
- Review loop dan findings.
- Versioning dokumen.
- Approval per versi dan independensi CV/CL.
- Render LaTeX, compile PDF, PDF QA.
- Penamaan file dan export record.

**Tidak bertanggung jawab:**

- Eligibility dan fit (domain eligibility).
- Fetch job (domain discovery).
- Approval UI (domain frontend; aksi tetap backend).
- Instalasi Tectonic (D6).

---

## 2. Input

- Profil confirmed + evidence.
- `job_posting_version` + requirement.
- Eligibility assessment dan fit assessment (fit hanya untuk `eligible`).
- Preferensi bahasa.
- Template dan prompt version.

---

## 3. Aturan Tailoring

| Boleh | Tidak boleh |
|---|---|
| Ubah urutan pengalaman, proyek, skill, dan bullet | Tambah perusahaan, jabatan, tanggal, gelar, sertifikasi |
| Pilih pengalaman/proyek yang relevan | Mengarang pengalaman, tanggung jawab, atau angka |
| Ringkas peran lama | Menghilangkan peran relevan untuk menyembunyikan gap |
| Sesuaikan redaksi secara akurat | Keyword stuffing atau klaim menyesatkan |
| Gunakan kata kunci yang didukung bukti | Mengubah level kemampuan tanpa bukti |
| Sesuaikan summary | Klaim "expert" tanpa bukti eksplisit |

Aturan:

- Setiap klaim penting harus dapat ditelusuri ke fakta Master CV atau `user_declaration`.
- Persyaratan yang tidak didukung bukti ditampilkan sebagai gap, bukan ditutup dengan klaim.
- Semua peran tetap tersedia di sumber; CV turunan boleh meringkas peran tidak relevan, tetapi tidak memalsukan tanggal.
- Perubahan pengguna pada dokumen turunan melewati validasi integritas yang sama.
- Bahasa mengikuti bahasa lowongan bila memungkinkan (K16, D19); bila tidak, tampilkan pilihan.

---

## 4. Pipeline

1. Eligibility gate (harus `eligible`).
2. Fit score (hanya eligible).
3. Pilih bukti relevan; CV turunan tidak memuat seluruh profil.
4. Draft terstruktur (JSON), bukan teks bebas.
5. Integritas deterministik: bukti, angka, tanggal, gelar, nama perusahaan, blocklist klaim berlebihan.
6. Diff vs Master CV: item dipilih, dihilangkan, diringkas, diubah.
7. Render LaTeX (`.tex.j2` → `.tex`).
8. Compile Tectonic, timeout 120 detik.
9. PDF QA: halaman, font, link, metadata, glyph rusak.
10. Reviewer terisolasi.
11. Revisi maksimal 2 siklus.
12. Review pengguna; dokumen `In Review`.
13. Approval per versi (CV dan CL terpisah).
14. Ekspor hanya versi `Approved`.
15. Apply membuka halaman resmi.

### 4.1 Implementasi milestone 3D (deterministik, tanpa LaTeX)

Status implementasi:

| Langkah | Status |
|---|---|
| 1–6 | Diimplementasikan deterministik |
| 7-11 | Diimplementasikan 2026-10-21 (LaTeX, Tectonic, QA PDF; reviewer LLM D9 belum dijalankan) |
| 12-13 | Diimplementasikan (review deterministik + approval per versi) |
| 14 | Diimplementasikan (`/api/applications/{id}/exports`, migrasi `0012_export`) |
| 15 | Ada di UI (buka URL resmi), tanpa auto-submit |

Draft dibangun dari `profile_version.content` + job tanpa provider/model call. `provider`, `model`, dan `prompt_version` bernilai `null`; `template_version` hanya disimpan bila klien mengirimkannya.

Bentuk `content` (schema versi 1):

```json
{
  "schema_version": 1,
  "kind": "cv",
  "language": "en",
  "target": {"job_id": "...", "job_posting_version_id": "...", "title": "...", "company": "..."},
  "header": {"full_name": "...", "email": "...", "phone": "...", "location": "...", "links": []},
  "summary": {"text": "...", "evidence_ids": ["ev_..."]},
  "skills": [{"id": "...", "name": "...", "proficiency": null, "evidence_ids": []}],
  "experience": [{"id": "...", "company": "...", "title": "...", "location": null, "start": "...", "end": null,
    "bullets": [{"id": "...", "text": "...", "evidence_ids": [], "skills": []}]}],
  "projects": [{"id": "...", "name": "...", "role": null, "technologies": [], "description": null,
    "start": null, "end": null, "evidence_ids": []}],
  "education": [{"id": "...", "institution": "...", "degree": "...", "field": null, "start": null, "end": null, "evidence_ids": []}],
  "certifications": [{"id": "...", "name": "...", "issuer": null, "date": null, "evidence_ids": []}],
  "languages": [{"id": "...", "name": "...", "level": null, "evidence_ids": []}],
  "missing": ["personal.email", "summary"]
}
```

Cover letter memakai `greeting`, `paragraphs` (`kind: intent|claim`, `text`, `evidence_ids`), `signoff`, dan `signature`; tidak memakai `summary`/`skills`/`experience`.

Aturan implementasi:

- `missing` adalah daftar field yang tidak tersedia di profil. Draft tidak mengisi nilai tebakan.
- Setiap klaim faktual menyimpan `evidence_ids`; header personal tidak membawa evidence karena profil tidak menyimpannya.
- Hash versi = SHA-256 canonical JSON (`sort_keys`, separator rapat, UTF-8).
- Diff versi 1: `base: master_cv`, item `selected`/`omitted`/`summarized`.
- Diff revisi/regenerate: `base: document_version`, `base_document_version_id` versi induk, item `added`/`removed`/`changed` per path.
- Data wajib sebelum approval: `header.full_name` dan minimal satu dari `experience`, `projects`, `education`.
- Eligibility `status_outdated` memblokir generate, regenerate, dan approval.
- Review ulang versi yang sudah `approved` ditolak; buat versi baru.
- Review deterministik hanya membuktikan integritas yang bisa diperiksa tanpa model: data wajib, klaim membawa evidence, dan evidence ada di `evidence_index`. Ini bukan pengganti reviewer LLM.

---

## 5. Traceability

```text
Master CV file (sha256)
  → extraction run
  → profile version (confirmed)
  → job + job_posting_version
  → eligibility assessment
  → fit assessment (hanya eligible)
  → tailored CV version
  → cover letter version
  → user edits + approval per version
  → export record (document_version_id + content_hash + filename)
```

Setiap dokumen turunan menyimpan:

- `master_cv_id`
- `profile_version_id`
- `job_id` + `job_posting_version_id`
- `eligibility_assessment_id`
- `fit_assessment_id`
- `prompt_version`, `template_version`, `provider`, `model`
- daftar `evidence_id` per klaim penting
- riwayat edit dan approval
- `content_hash`, status, referensi ekspor

---

## 6. Approval per Versi

- Setiap CV/CL memiliki `document_version_id`, `kind`, nomor versi, dan `content_hash` unik.
- Approval hanya untuk versi yang disetujui pengguna.
- Edit/regenerate membuat versi baru `Draft` atau `In Review`.
- Approval versi lama tetap tersimpan, tetapi tidak berlaku untuk versi baru.
- Approval CV dan CL independen.
- Ekspor harus mereferensikan `document_version_id` + `content_hash`.
- Versi baru yang belum disetujui tidak boleh menggantikan file final.
- Riwayat approval mencatat versi, keputusan, waktu, catatan.
- Dokumen dapat ditelusuri ke versi profil, lowongan, dan sumbernya.

Implementasi milestone 3D:

- Approval ditolak `409` bila hash tidak cocok, review belum selesai, eligibility bukan `eligible` atau `status_outdated`, atau data wajib belum lengkap.
- `approved`/`rejected`/`changes_requested` dicatat sebagai record baru (append-only). `rejected`/`changes_requested` tidak mengubah status versi dari `in_review`.
- Approval ulang dengan versi + hash + keputusan sama mengembalikan record yang sama, bukan membuat duplikat.
- Versi yang sudah `approved` tidak bisa di-review ulang atau diganti keputusannya; buat versi baru.
- Approval menghitung ulang hash dari `content_json` sebelum mencatat keputusan.
- Revisi menolak perubahan `kind`, `schema_version`, `target`, `missing`, `language`, dan `evidence_ids`, serta memvalidasi tipe struktur dasar konten.- Approval versi lama tetap berlaku untuk versi itu saja. Versi baru selalu mulai `draft` dengan `review_status = not_started`.
- Approval tidak menghapus findings.
- Ekspor belum diimplementasikan; gate ekspor baru diuji pada approval.

---

## 7. Reviewer dan Quality Gates

Reviewer menerima:

- Requirement terstruktur.
- Hasil eligibility.
- Subset evidence.
- Dokumen final (teks + JSON).
- Laporan QA deterministik.

Reviewer tidak menerima alasan penulis, draft sebelumnya, atau instruksi "buat agar lolos".

Pemeriksaan: relevansi, fakta, klaim berlebihan, bahasa, ATS, konsistensi, format, prioritas, eligibility, approval, Apply.

Severity:

| Level | Definisi | Efek |
|---|---|---|
| `blocker` | Fakta salah, fabrikasi, PDF rusak, perusahaan/jabatan salah | Wajib diperbaiki |
| `major` | Must-have tidak terjawab, ATS rusak, CV/CL bertentangan | Wajib diperbaiki |
| `minor` | Kalimat lemah, format kurang rapi | Boleh tersisa, dilaporkan |
| `nit` | Preferensi gaya | Diabaikan |

Kriteria lulus: 0 `blocker`, 0 `major`.

Siklus:

- Maksimal 2 siklus revisi (3 review: awal + revisi 1 + revisi 2).
- Berhenti lebih awal bila tidak ada `blocker`/`major` atau tidak ada perubahan bermakna.
- Berhenti bila perbaikan menuntut fakta baru; laporkan `unresolved`.
- Compile gagal 2 kali → `tex_only`.
- Reviewer gagal → `review_unavailable`; dokumen tidak siap.
- Approve pengguna tidak menghapus temuan; laporan tetap menampilkan sisa temuan.

Status milestone 3D: reviewer LLM terisolasi belum diimplementasikan (D9 belum dijalankan). Yang berjalan adalah review deterministik:

- `blocker`: data wajib tidak ada, atau `evidence_id` tidak ditemukan di `evidence_index`.
- `major`: klaim faktual tanpa `evidence_id`.
- Verdict `pass` hanya bila 0 `blocker` dan 0 `major`; selain itu `changes_required`.
- `review_unavailable`, `unresolved`, dan siklus revisi otomatis berbasis model belum dihasilkan.
- Batas 3 siklus review per versi ditegakkan; siklus ke-4 ditolak `409 conflict` dengan `details[].code = review_cycle_limit`.

---

## 8. Format Dokumen

- CV maksimal 2 halaman; cover letter 1 halaman.
- Satu kolom, ATS-friendly, tanpa foto default.
- Template `article`, tanpa tabel layout.
- Font TeX Gyre Termes/Heros via `fontspec`.
- Matikan ligatur umum (`Ligatures=NoCommon`).
- Margin 0.7 inci; ukuran 10.5–11 pt.
- Section standar: Summary, Skills, Experience, Projects, Education, Certifications.
- `hyperref` dengan `pdftitle` dan `pdfauthor`; link aktif.
- Compile: `tectonic -X compile cv.tex --outdir build`.

Tectonic belum terpasang. Toolchain ini rencana, bukan verifikasi.

---

## 9. Penamaan File

Format:

```text
CV_<Candidate>_<Company>_<Position>.pdf
Cover_Letter_<Candidate>_<Company>_<Position>.pdf
```

Aturan:

- Nama kandidat dari profil confirmed; perusahaan dan posisi dari lowongan.
- Bersihkan karakter ilegal, separator, karakter kontrol, spasi berulang. Gunakan underscore.
- Tangani nama kosong/terlalu panjang; fallback jelas; batasi panjang.
- Tabrakan nama memakai suffix stabil, misalnya potongan `job_id`.
- Pengguna dapat mengubah nama sebelum ekspor.
- Perubahan nama tidak mengubah isi atau approval.
- Master CV tidak boleh diganti nama atau ditimpa.
- Ekspor berasal dari versi approved, bukan PDF terbaru di direktori.
- PDF gagal → error jelas; jangan `Exported`.

---

## 10. Output Bundle

```text
data/applications/<app_id>/
  manifest.json
  job.json
  job_posting_version.json
  requirements.json
  eligibility.json
  assessment.json
  cv/v1/cv.json
  cv/v1/cv.tex
  cv/v1/cv.pdf
  cv/v1/diff.json
  cover_letter/v1/cover_letter.json
  cover_letter/v1/cover_letter.tex
  cover_letter/v1/cover_letter.pdf
  review/cycle-1.json
  review/cycle-2.json
  edits.jsonl
  approvals/cv-v1.json
  approvals/cover_letter-v1.json
  exports/CV_<Candidate>_<Company>_<Position>.pdf
  exports/Cover_Letter_<Candidate>_<Company>_<Position>.pdf
  exports/manifest.json
  report.md
```

`report.md` memuat: ringkasan lowongan, sumber + waktu fetch, `priority_tier` + alasan, eligibility + alasan, `fit_score` + komponen, requirement terpenuhi/tidak, gap, perubahan dari Master CV, temuan reviewer, status approval per dokumen, nama file ekspor, keputusan pengguna.

---

## 11. Error Handling dan State

| Kondisi | Perilaku |
|---|---|
| Eligibility bukan `eligible` | Blokir dokumen |
| Kutipan/bukti tidak cocok | Tolak klaim; tampilkan gap |
| Compile gagal | Simpan `.tex` + log; retry maks 2; lalu `tex_only` |
| PDF QA gagal | Jangan `Exported` |
| Reviewer gagal | `review_unavailable` |
| Edit setelah approval | Versi baru belum disetujui |
| Nama file ilegal | Sanitasi/fallback |
| Nama tabrakan | Suffix stabil |
| Ekspor versi salah | Tolak; cek ID + hash |

---

## 12. Keamanan dan Privasi

- Dokumen tidak masuk log.
- Prompt/respons tidak disimpan mentah default.
- Nama file tidak dipakai sebagai path.
- Ekspor hanya versi approved.
- Jangan menimpa Master CV.
- HTML eksternal tidak dirender di dokumen tanpa sanitasi.
- Jangan mengirim seluruh profil ke provider; kirim irisan relevan.

---

## 13. Acceptance dan Verifikasi

Mengacu `PLAN.md` §14:

- Kriteria 14: approval per versi; CV/CL independen; ID + hash.
- Kriteria 15: edit/regenerate membuat versi baru belum disetujui.
- Kriteria 16: ekspor hanya approved; versi baru tidak menggantikan file final.
- Kriteria 17: nama file sesuai format.
- Kriteria 18: nama aman; tabrakan ditangani; nama dapat diedit.
- Kriteria 19: Master CV tetap.
- Kriteria 20: isolasi antar lowongan.
- Kriteria 21: `Outdated` tanpa regenerasi otomatis.
- Kriteria 22: 0 klaim tanpa evidence; 0 angka/tanggal/gelar baru; gap ditampilkan.
- Kriteria 23: semua `blocker` seeded defects tertangkap; maks 2 siklus; sisa temuan dilaporkan.

Verifikasi: integration test dengan fixture, seeded defects, test approval/export, PDF QA, 3 uji manual Phase 3.

---

## 14. Keputusan dan `OPEN`

Final: K7, K8, K13, K16, K19, K20, K22; D5, D12, D19.

`OPEN`:

- D6 (instalasi Tectonic) — memblokir Phase 3 saat instalasi.
- D21 (override `ineligible`) — bila diimplementasikan.
- D9 (model reviewer berbeda).
- Kalibrasi kualitas reviewer.
- Ambang dan bobot fit memengaruhi tailoring.

---

## 15. Referensi PLAN.md

- §4.3 `/apply` (alur, preflight, pipeline, override, approval, penamaan, format, bundle)
- §7 Reviewer dan Quality Gates
- §9.4 Riwayat dan referensi sumber
- §11 Validasi per tahap (generate, diff, LaTeX, PDF QA, review, approval, export)
- §13 Phase 3
- §14 kriteria 14–23
- §15.4 D6, D9, D19, D21
