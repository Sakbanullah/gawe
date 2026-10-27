# DATABASE — MySQL, Model Data, dan Persistensi

**Domain:** MySQL 8, migrasi, model data, relasi, transaksi, koneksi, persistensi.
**Source of Truth terkait:** [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md), [`../source-of-truth/ARCHITECTURE.md`](../source-of-truth/ARCHITECTURE.md).
**Referensi master:** `PLAN.md` §4.1, §4.3, §9, §12.

Keputusan implementasi database (MySQL, schema test terisolasi, lifecycle koneksi) disetujui pengguna 2026-10-19. Konflik C8 terhadap `PLAN.md` sudah ditutup; catatan penutupannya ada di [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) §7 C8.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Skema MySQL, migrasi, dan repository.
- Relasi entity dan foreign key.
- Transaksi dan konsistensi status.
- Lifecycle koneksi: satu koneksi per request, tanpa koneksi global bersama.
- Persistensi metadata, histori run, approval, dan ekspor.
- Pencarian teks (bila dipakai).
- Versioning append-only dan content-addressed storage.

**Tidak bertanggung jawab:**

- Aturan bisnis eligibility/fit/ranking.
- Format file PDF/LaTeX.
- Kontrak API.

---

## 2. Format Penyimpanan

| Media | Isi |
|---|---|
| MySQL 8 | Index, relasi, status, histori run, pencarian teks |
| File | Master CV asli, dokumen turunan, artefak LaTeX/PDF, laporan |
| JSON | Bentuk kanonik untuk profil, eligibility, assessment, dokumen; disimpan di kolom `*_json` dan tetap mudah di-diff saat diekspor |

MySQL 8.0.30 (Laragon, `127.0.0.1:3306`, `utf8mb4`) adalah server yang dipakai.

Pencarian: MySQL `FULLTEXT` tersedia, tetapi **belum dipakai**. Keputusan apakah pencarian memakai `FULLTEXT`, tabel turunan, atau filter biasa masih `OPEN` (lihat §13).

---

## 3. Entity

Sumber: `PLAN.md` §9.2. Tabel Phase 1–3D yang sudah ada di migrasi: `schema_version` sampai `document_approval`. Tabel yang belum dibuat ditandai *rencana*.

| Entity | Isi penting | Kunci | Relasi |
|---|---|---|---|
| `schema_version` | Versi migrasi yang sudah diterapkan, waktu | `version` | — |
| `consent_record` | Jenis consent, provider, snapshot model, teks, waktu | `consent_id` | — |
| `llm_call` | Role, provider, model, prompt hash, token, biaya, response hash | `call_id` | — |
| `master_cv` | File asli, hash, status, profil aktif | `master_cv_id`, `sha256` unik | Banyak profile version |
| `source_document` | Hash, MIME, halaman, blok teks | `doc_id` | Milik Master CV |
| `profile_version` | Versi, status, hash, JSON, `master_cv_id` | `profile_version_id`, unik `(profile_id, version)` | Banyak assessment |
| `profile_correction` | Field, nilai lama/baru, waktu, alasan | `correction_id` | Profile version |
| `profile_decision` | Gate, pilihan, alasan, waktu | `decision_id` | Profile version |
| `task` | Tipe, status, progress, hasil, error | `task_id` | Application |
| `source_registry` | Company, URL, metode akses, status verifikasi, ToS, prioritas, jadwal, kuota, kesehatan | `source_id` | Menghasilkan job |
| `job` | Sumber, ID sumber, URL kanonik, `apply_url` terverifikasi, company, title, lokasi, work mode, tanggal, `posted_at_epoch` untuk sort SQL | `(source, source_job_id)`, `canonical_url` | Banyak versi posting |
| `job_posting_version` | `content_hash`, deskripsi, `fetched_at`, URL, `analyzed_at`, status | UUID | Milik job |
| `job_requirement` | Kind, teks, skill, bobot, kutipan, constraint, sumber ekstraksi | UUID | Milik posting version |
| `eligibility_assessment` | Status, checks, alasan, confidence, `status_outdated` | UUID | Posting version + profile version |
| `eligibility_check` | Requirement, hasil, kutipan, bukti | UUID | Eligibility assessment |
| `fit_assessment` | `fit_score`, verdict, confidence, komponen, gap, `status_outdated` | UUID | Posting version + profile version |
| `ranking_run` | Preferensi, `tie_window`, urutan, waktu | UUID | Profile version |
| `job_rank` | Urutan ranking yang sudah di-flatten: `(ranking_run_id, job_id, section, position)`; query surface untuk `/api/matches` | `(ranking_run_id, job_id)` | Milik ranking run |
| `application` | Workspace per lowongan, `profile_version_id` snapshot, waktu; status ringkasan dihitung saat baca, bukan disimpan | UUID, unik `job_id` | Job, profile version |
| `document_version` | Kind, versi, `content_json`, `content_hash`, `diff_json`, `evidence_json`, review status/verdict/cycle/findings, parent; tidak ada path TeX/PDF | `(application, kind, version)` | Milik application |
| `document_edit` *(rencana)* | Sebelum/sesudah, sumber (user/LLM), waktu | UUID | Document version |
| `document_approval` | `document_version_id`, `document_hash`, kind, keputusan, catatan, waktu; append-only | UUID | Document version + application |
| `export_record` *(rencana)* | `document_version_id`, `document_hash`, nama file, path, waktu, status | UUID | Document version + application |
| `review_run` *(rencana)* | Siklus, provider, model, prompt hash, verdict | UUID | Document version |
| `finding` *(rencana)* | Severity, category, lokasi, kutipan, problem, fix, status | UUID | Review run |
| `human_decision` | Gate, pilihan, alasan, waktu | UUID | Application/profile |
| `config_snapshot` | Provider/model mapping, prompt version, template version | UUID | Application/run |
| `run_event` | Workflow, stage, durasi, token, biaya, error | UUID | Application/run |
| `search_preference` | JSON preferensi, versi | UUID | — |

---

## 4. Relasi

```text
MASTER_CV 1─* PROFILE_VERSION
MASTER_CV 1─* SOURCE_DOCUMENT
PROFILE_VERSION 1─* ELIGIBILITY_ASSESSMENT
PROFILE_VERSION 1─* FIT_ASSESSMENT
JOB 1─* JOB_POSTING_VERSION
JOB_POSTING_VERSION 1─* JOB_REQUIREMENT
JOB_POSTING_VERSION 1─* ELIGIBILITY_ASSESSMENT
JOB_POSTING_VERSION 1─* FIT_ASSESSMENT
JOB 1─* APPLICATION
PROFILE_VERSION 1─* APPLICATION
APPLICATION 1─* DOCUMENT_VERSION
DOCUMENT_VERSION 1─* DOCUMENT_APPROVAL
APPLICATION 1─* DOCUMENT_APPROVAL
DOCUMENT_VERSION 1─* DOCUMENT_EDIT        (rencana)
DOCUMENT_VERSION 1─* EXPORT_RECORD        (rencana)
DOCUMENT_VERSION 1─* REVIEW_RUN           (rencana)
APPLICATION 1─* HUMAN_DECISION
APPLICATION 1─* RUN_EVENT
```

Foreign key memakai `InnoDB`. Penghapusan induk tidak memakai `ON DELETE CASCADE` default: purge menghapus row anak secara eksplisit agar tidak ada data hilang tanpa jejak.

---

## 5. Identitas dan Duplikasi

- ID internal: UUIDv4 + timestamp. Tampilan: `job_7f3a2c91`.
- Master CV: SHA-256, write-once.
- Job: exact key + canonical URL + fingerprint.
- Aplikasi: satu application (workspace) per `job_id`.
- Dokumen: identitas `(application, kind, version)`.
- Approval dan ekspor merujuk `document_version_id` + `content_hash`.

### Dedupe job

- Exact: `(source, source_job_id)` dan `canonical_url`.
- Lintas sumber: `sha256(company_norm + title_norm + city_norm + employment_type)`.
- Fuzzy: `difflib.SequenceMatcher` dalam blok company/location, threshold 0.92.
- Simpan `duplicate_of`; jangan hapus data.

---

## 6. Immutability dan Append-Only

- Semua versi append-only.
- Master CV disimpan immutable dan content-addressed: `data/master_cv/<sha256>/`.
- Upload baru membuat record baru; versi lama tetap ada.
- `profile/active.json` menunjuk versi aktif; rollback ke versi confirmed sebelumnya.
- Koreksi disimpan di `profile/corrections.jsonl`; keputusan di `profile/decisions.jsonl`.
- Dokumen tidak menimpa versi lama; regenerate membuat versi baru.
- Approval versi lama tetap tersimpan sebagai riwayat.
- Ekspor tidak menimpa file final yang sudah disetujui.

---

## 7. Transaksi, Konsistensi, dan Koneksi

### 7.1 Transaksi

- Operasi multi-tabel memakai satu transaksi eksplisit (`with connection:`).
- Operasi yang menulis beberapa tabel dalam satu alur bisnis harus berada dalam blok transaksi yang sama, termasuk penulisan audit (`profile_decision`, `llm_call`).
- Jangan menulis sebagian saat validasi gagal.
- Foreign key menjaga isolasi dokumen antar aplikasi.
- Checkpoint orchestrator disimpan agar resume konsisten.
- Status dokumen adalah sumber kebenaran; status aplikasi diproyeksikan.
- Penandaan `Outdated` disimpan sebagai status/field, bukan dengan menghapus hasil lama.
- Restore memvalidasi schema version sebelum menulis.

### 7.2 Lifecycle koneksi (FastAPI)

- **Tidak ada koneksi global bersama** di `app.state`.
- Setiap request HTTP membuka koneksi sendiri lewat middleware, menaruhnya di `request.state.db`, lalu menutupnya di `finally`.
- `create_app(config, connection=...)` menerima koneksi injeksi hanya untuk test; produksi selalu membuka koneksi per request.
- Startup hanya menjalankan migrasi dengan koneksi sementara yang langsung ditutup. Migrasi gagal berarti server tidak boleh melayani request.
- Repository dan service menerima koneksi sebagai parameter; tidak ada singleton yang menyimpan koneksi.
- Lock Python (`RLock` atau sejenisnya) **bukan** pengganti transaksi atau lifecycle koneksi.
- Autocommit aktif di level driver; batas transaksi ditentukan oleh blok `with connection:`, sehingga commit/rollback tidak bergantung pada urutan pemanggilan.
- Pooling koneksi belum dipakai. Satu request satu koneksi cukup untuk aplikasi single-user lokal.

### 7.3 Konfigurasi

`[database]` di `config.toml`: `host`, `port`, `user`, `password_env`, `name`, `charset`.

- Password tidak ditulis di config atau `.env.example`. Nilai dibaca dari environment (`GAWE_DB_PASSWORD` default) atau `password` di config lokal yang di-gitignore.
- Nama schema divalidasi: hanya huruf, angka, dan `_`, maksimal 64 karakter, dan bukan schema sistem.

---

## 8. File dan Direktori

Mengikuti `PLAN.md` §4.3 dan §9.5.

```text
data/master_cv/<sha256>/original.pdf
profile/versions/0001.json
profile/active.json
profile/corrections.jsonl
profile/decisions.jsonl
data/applications/<app_id>/
  manifest.json, job.json, job_posting_version.json, requirements.json,
  eligibility.json, assessment.json,
  cv/v1/{cv.json,cv.tex,cv.pdf,diff.json},
  cover_letter/v1/{cover_letter.json,cover_letter.tex,cover_letter.pdf},
  review/cycle-1.json, review/cycle-2.json,
  edits.jsonl, approvals/cv-v1.json, approvals/cover_letter-v1.json,
  exports/{...}.pdf, exports/manifest.json, report.md
data/runs/
logs/
```

`exports/manifest.json` mencatat `document_version_id`, `content_hash`, nama file, waktu, status.

**Gap:** `PLAN.md` §4.1 menyebut semua file di `data/`, sedangkan `profile/` dan `logs/` berada di root menurut §9.5/§12. Belum diselesaikan.

---

## 9. Migrasi

- Migrasi versioned di `backend/src/gawe/db/migrations/`, nama `NNNN_nama.sql`.
- Setiap file migrasi idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX` yang aman diulang) agar migrasi yang gagal di tengah bisa dijalankan ulang.
- Setiap pernyataan dijalankan satu per satu; kegagalan menghentikan migrasi dan versi tidak dicatat.
- DDL MySQL melakukan implicit commit, sehingga rollback otomatis tidak diandalkan. Karena itu urutan penulisan `schema_version` dilakukan setelah semua pernyataan berhasil, dan setiap pernyataan harus idempotent.
- Schema version disimpan dan divalidasi saat restore.
- Jangan mengubah data kandidat tanpa backup.
- Perubahan schema harus disetujui sebelum implementasi.

Detail DDL domain penuh belum ditetapkan (`OPEN`). Yang sudah ada: `0001_initial.sql`, `0002_setup.sql`, dan `0003_consent.sql` (kolom `text_version`, `text_sha256`, `data_classes_json` pada `consent_record`; row lama mendapat nilai kosong sehingga dianggap kedaluwarsa dan memerlukan consent baru). `0003_consent.sql` memakai pemeriksaan `information_schema.columns` sebelum setiap `ALTER TABLE ... ADD COLUMN`, sehingga apply parsial (kolom sudah ada tetapi `schema_version` belum tercatat) dapat dijalankan ulang tanpa error dan tanpa menyentuh data.

---

## 10. Error Handling

| Kondisi | Perilaku |
|---|---|
| Migrasi gagal | Jangan serve; laporkan |
| Constraint violation | Tolak transaksi; pesan aman |
| File hilang | Laporkan; jangan menebak isi |
| Hash tidak cocok | Tolak ekspor/restore |
| Duplikat | Simpan `duplicate_of`; jangan hapus |
| Restore schema beda | Tolak sebelum menulis |

Constraint yang diuji: `sha256` unik di `master_cv`, unik `(profile_id, version)`, maksimal satu `profile_version` aktif, dan foreign key `source_document`/`profile_version` → `master_cv`.

---

## 11. Keamanan dan Privasi

- Kredensial database hanya di environment/config lokal; tidak di-commit.
- Database dan file di-gitignore.
- Path berasal dari ID/hash, bukan nama pengguna.
- Jangan menyimpan prompt/respons mentah secara default.
- Log tidak memuat isi dokumen/PII.
- Backup tanpa secret.
- Purge menghapus row dan file terkait.
- ACL direktori dan BitLocker direkomendasikan.
- Schema test memakai prefix `gawe_test_`; operasi `DROP DATABASE` menolak nama tanpa prefix itu.

Detail di [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md).

---

## 12. Acceptance dan Verifikasi

- Upload ulang tidak menimpa Master CV.
- Versi profil append-only; rollback bekerja.
- Dokumen lowongan A tidak menimpa B.
- Approval dan ekspor merujuk ID/hash yang benar.
- Restore menolak schema version yang tidak cocok.
- Purge menghapus data terkait.
- Dedupe exact + fuzzy teruji pada fixture.
- Constraint unik dan foreign key menolak data tidak sah.
- Transaksi multi-tabel rollback penuh saat satu penulisan gagal.

Verifikasi: unit test repository, migration test, integration test terhadap schema MySQL khusus test, fixture.

---

## 13. Keputusan dan `OPEN`

Final: K8, K20, K21, K22, K26; D5, D13. Keputusan implementasi 2026-10-19: MySQL 8 (bukan PostgreSQL), schema test terisolasi, koneksi per request.

`OPEN`: DDL domain penuh, strategi migrasi awal untuk data existing, apakah pencarian memakai `FULLTEXT` dan untuk apa, retensi (D10), enkripsi (D8), connection pooling.

---

## 14. Referensi PLAN.md

- §4.1 Master CV record, versioning, corrections
- §4.3 output bundle dan export manifest
- §9.1 Format
- §9.2 Entitas
- §9.3 Identitas dan duplikasi
- §9.4 Riwayat dan referensi sumber
- §9.5 Pemisahan data
- §9.6 Backup, restore, hapus
- §12 Struktur repo (`db/`, `data/`, `profile/`)
