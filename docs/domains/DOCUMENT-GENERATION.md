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
3. Rencana penyesuaian: disusun deterministik dari fit dan bukti yang sudah ada, disetujui pengguna. Persetujuan rencana terpisah dari approval dokumen dan consent cloud. Rincian di §4.0.
4. Pilih bukti relevan sesuai rencana; CV turunan tidak memuat seluruh profil.
5. Draft terstruktur (JSON), bukan teks bebas.
6. Self-check deterministik: bukti, angka, tanggal, gelar, nama perusahaan, blocklist klaim berlebihan, gap tidak muncul sebagai klaim, panjang, dan kata kunci relevan. Hasil dan daftar perubahan terikat ke `document_version_id`. Dokumen yang gagal tidak dapat diajukan untuk approval.
7. Diff vs Master CV: item dipilih, dihilangkan, diringkas, diubah.
8. Render LaTeX (`.tex.j2` → `.tex`).
9. Compile Tectonic, timeout 120 detik.
10. PDF QA: halaman, font, link, metadata, glyph rusak.
11. Reviewer terisolasi (role `review`), digabung dengan review deterministik.
12. Revisi otomatis sampai gate terpenuhi, maksimum 5 iterasi per dokumen.
13. Review pengguna; dokumen `In Review`.
14. Approval per versi (CV dan CL terpisah).
15. Ekspor hanya versi `Approved`.
16. Apply membuka halaman resmi.

### 4.0 Rencana penyesuaian (langkah 3)

Rencana disimpan per lowongan dan terikat ke `job_posting_version_id` serta `profile_version_id` yang dipakai saat disusun. Isi rencana:

- `sections`: bagian CV yang dipakai, diringkas, atau dihilangkan, beserta alasan dan `evidence_ids` pendukung.
- `keywords`: kata kunci dari requirement yang didukung bukti profil. Kata kunci tanpa bukti tidak masuk rencana.
- `gaps`: requirement yang tidak didukung bukti. Gap dibiarkan terbuka dan tampil di dokumen, bukan ditutup dengan klaim.
- `language`: bahasa dokumen, mengikuti bahasa lowongan bila dikenali.

Aturan:

- Rencana disusun deterministik dari `fit_assessment` (komponen, gap) dan `evidence_index` profil. Tidak ada panggilan model, sehingga tidak membutuhkan consent cloud.
- Persetujuan rencana dicatat terpisah (`plan_approval`) dan tidak memberi approval dokumen apa pun.
- Rencana yang menunjuk versi profil atau versi posting lain berstatus `outdated`; generate ditolak sampai rencana disusun ulang.
- Perubahan rencana setelah disetujui membuat versi rencana baru yang harus disetujui lagi.
- Isi rencana adalah data kandidat: tidak boleh masuk log, hanya metadata (`plan_id`, `job_id`, versi, hash, status).

### 4.1 Implementasi milestone 3D (deterministik, tanpa LaTeX)

Status implementasi:

| Langkah | Status |
|---|---|
| 1–2 | Diimplementasikan |
| 3 | Diimplementasikan: rencana deterministik + persetujuan pengguna |
| 4–7 | Diimplementasikan deterministik, dengan role `write` opsional di atasnya |
| 8–12 | Diimplementasikan 2026-10-21 (LaTeX, Tectonic, QA PDF; reviewer LLM role `review` aktif bila provider nyata) |
| 13–14 | Diimplementasikan (review deterministik + reviewer LLM + approval per versi) |
| 15 | Diimplementasikan (`/api/applications/{id}/exports`, migrasi `0012_export`) |
| 16 | Ada di UI (buka URL resmi), tanpa auto-submit |

Draft dibangun dari `profile_version.content` + job. Bila role `write` aktif, konten datang dari model; bila tidak, atau bila keluaran model gagal validasi, draft deterministik dipakai dan `provider`/`model`/`prompt_version` mencerminkan sumber yang benar-benar dipakai.

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

Kriteria lulus: 0 `blocker`, 0 `major`, dan skor reviewer minimal sama dengan ambang (default 8.0, sementara sampai kalibrasi).

Siklus:

- Maksimum 5 iterasi per dokumen. Satu iterasi = satu versi dibuat + satu review.
- Penghitung iterasi bersifat global per dokumen: nilainya adalah posisi versi dalam rantai `parent_document_version_id`, bukan `review_cycle` per baris. Versi baru tidak mereset penghitung.
- Berhenti lebih awal bila gate terpenuhi, bila kenaikan skor antar iterasi < 0.5, bila reviewer tidak menghasilkan skor, atau bila perbaikan menuntut fakta baru.
- Iterasi berhenti tanpa lulus → `passed = false` dan `stop_reason` di `passed`/`stagnated`/`iteration_limit`/`review_unavailable`/`review_skipped`. Tidak pernah dilaporkan sebagai sukses.
- Compile gagal 2 kali → `tex_only`.
- Reviewer gagal → `review_unavailable`; dokumen tidak siap dan tidak bisa di-approve.
- Approve pengguna tidak menghapus temuan; laporan tetap menampilkan sisa temuan.
- Approval hanya untuk versi dengan `review_verdict = pass` dan skor memenuhi ambang. Verdict `unresolved`, `changes_required`, dan `review_unavailable` semuanya memblokir approval.

Status implementasi 2026-10-21 (D9 diputuskan):

- Role `write` menghasilkan konten JSON yang bentuknya identik dengan `draft.build()`; hasil model yang gagal validasi jatuh ke draft deterministik dan mencatat `fallback_code`.
- Role `review` menghasilkan `verdict`, `overall_score`, `dimension_scores` (clarity, relevance, credibility, differentiation, professional_quality), dan `findings`.
- Review deterministik (`documents/review.py`, `documents/factcheck.py`) tetap berjalan dan digabung dengan temuan reviewer LLM. Blocker atau major dari salah satu lapisan menggagalkan dokumen, berapa pun skornya.
- Identitas (`header`, `target`, `signature`, `schema_version`, `kind`, `language`) selalu diambil dari data tepercaya, bukan dari keluaran model.
- Loop otomatis hanya berjalan bila prompt reviewer tersedia untuk root yang dipakai. Tanpa reviewer, versi dibiarkan belum direview dan endpoint review eksplisit tetap memutuskan.
- Batas 5 iterasi ditegakkan di `regenerate` dan `run_review`: permintaan berikutnya ditolak `409 conflict` dengan `details[].code = iteration_limit`.
- Ambang skor belum dikalibrasi terhadap sampel yang disetujui; nilai 8.0 adalah default sementara, bukan hasil kalibrasi.

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
