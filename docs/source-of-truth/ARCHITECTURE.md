# ARCHITECTURE — Arsitektur Sistem dan Batas Modul

**Source of Truth untuk:** arsitektur sistem, batas antarmodul, aliran data, runtime lokal, invariant arsitektur.
**Bukan Source of Truth untuk:** status keputusan (lihat [`DECISIONS.md`](DECISIONS.md)), kontrak endpoint (lihat [`API-CONTRACTS.md`](API-CONTRACTS.md)), aturan bisnis (lihat [`PRODUCT.md`](PRODUCT.md)).
**Referensi master:** `PLAN.md` §1, §5, §6, §8, §9, §10, §12, §13.

---

## 1. Konteks Sistem

Gawe adalah **aplikasi web lokal single-user**:

- Satu proses lokal melayani API JSON dan aset frontend hasil build.
- Frontend: React + TypeScript + Vite + Mantine (SPA).
- Backend: Python + FastAPI + Pydantic.
- Penyimpanan: MySQL 8 (Laragon) + file.
- LLM: lapisan adapter provider-agnostic; provider belum ditetapkan.
- Tidak ada deployment publik, cloud server, multi-user, atau queue eksternal.
- Bind hanya ke `127.0.0.1`.

```text
Browser lokal
  └─ React SPA (TypeScript, Vite, Mantine)
       └─ HTTP JSON + CSRF token
            └─ FastAPI lokal (127.0.0.1)
                 ├─ Orchestrator (state machine, gate)
                 ├─ Service layer per workflow
                 ├─ Domain: ingest, profile, jobs, eligibility, match, ranking,
                 │          generate, review, export, status
                 ├─ LLM gateway → provider adapter → provider eksternal/lokal
                 ├─ Security: URL guard, redaction, secrets, consent, sanitize, CSRF
                 ├─ MySQL 8 (index, relasi, status, histori; FULLTEXT opsional)
                 └─ data/ + profile/ (file immutable, artefak, laporan)
```

---

## 2. Prinsip Arsitektur

1. **Satu orchestrator, banyak fungsi.** LLM dipanggil sebagai role dengan schema dan validator, bukan agent otonom.
2. **Backend adalah sumber kebenaran.** Workflow, validasi, persistensi, eligibility, fit, ranking, approval, status, dan penamaan file dihitung di backend.
3. **Frontend hanya view/control.** Frontend tidak menghitung aturan bisnis otoritatif dan tidak menyimpan salinan otoritatif data.
4. **Pipeline deterministik lebih dulu.** LLM hanya di titik yang membutuhkan penalaran bahasa.
5. **Provider-agnostic.** Pipeline dan prompt tidak mengimpor SDK vendor. Perbedaan vendor hanya di adapter.
6. **Append-only dan immutable.** Master CV write-once; versi profil, dokumen, approval, dan ekspor tidak saling menimpa.
7. **Konten eksternal adalah data tidak tepercaya.** Job description, HTML, dan dokumen tidak boleh diperlakukan sebagai instruksi.
8. **Tidak ada auto-submit.** Apply membuka halaman resmi; pengguna submit sendiri.

---

## 3. Komponen dan Tanggung Jawab

| Komponen | Tanggung jawab | Bentuk | Domain terkait |
|---|---|---|---|
| React SPA | Halaman, state UI, konsumsi API | React + TypeScript + Vite + Mantine | [`../domains/FRONTEND.md`](../domains/FRONTEND.md) |
| HTTP API | Kontrak JSON, validasi request, panggil service | FastAPI + Pydantic + OpenAPI | [`../domains/BACKEND.md`](../domains/BACKEND.md) |
| Orchestrator | Urutan tahap, gate, checkpoint, resume | State machine | [`../domains/SYSTEM.md`](../domains/SYSTEM.md) |
| Master CV store | Simpan file asli immutable + metadata | Deterministik, content-addressed | [`../domains/DATABASE.md`](../domains/DATABASE.md) |
| Document ingest | Baca file, ekstrak teks + locator | Deterministik, parser di subprocess + timeout | [`../domains/BACKEND.md`](../domains/BACKEND.md) |
| Profile extractor | Teks → fakta + kutipan | LLM role `extract` | [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md) |
| Profile merger | Koreksi, konflik, konfirmasi, versioning | Deterministik + manusia | [`../domains/BACKEND.md`](../domains/BACKEND.md) |
| Source registry + adapters | Kelola sumber, ambil data | Deterministik | [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md) |
| Normalizer + deduper | Seragamkan field, deteksi duplikat | Deterministik | [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md) |
| Priority classifier | Tier + alasan + confidence | Deterministik + LLM opsional | [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md) |
| Requirement parser | Must/nice/constraint | Pre-pass + LLM `classify` | [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md) |
| Eligibility evaluator | Status + alasan + kutipan + bukti | Deterministik + LLM terbatas | [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md) |
| Fit scorer | Skor + komponen + confidence | Deterministik + LLM | [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md) |
| Ranker | Urutan fit-first + tie-breaker | Deterministik | [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md) |
| Tailoring planner | CV turunan + cover letter | LLM `write` | [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md) |
| Diff builder | Bandingkan turunan vs Master CV | Deterministik | [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md) |
| Renderer + compiler | JSON → LaTeX → PDF | Deterministik + subprocess | [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md) |
| Deterministic QA | Cek isi dan PDF | Deterministik | [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md) |
| Reviewer | Kritik independen | LLM `review`, konteks terpisah | [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md) |
| Export service | Approval check, nama file, hash, record | Deterministik | [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md) |
| Status projector | Propagasi `Outdated`/`Failed` | Deterministik | [`../domains/SYSTEM.md`](../domains/SYSTEM.md) |
| Apply link resolver | URL resmi terverifikasi | Deterministik | [`../domains/BACKEND.md`](../domains/BACKEND.md) |
| LLM gateway | Role → model, validasi output | Adapter | [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md) |
| Security utilities | URL guard, redaction, secrets, consent, sanitize, CSRF | Deterministik | [`../domains/SECURITY-AND-PRIVACY.md`](../domains/SECURITY-AND-PRIVACY.md) |
| CLI admin | `doctor`, `backup`, `restore`, `purge` | Utilitas, bukan UI utama | [`../domains/SYSTEM.md`](../domains/SYSTEM.md) |

**Yang tidak dijadikan agent terpisah:** job parsing, dedupe, eligibility (deterministik dulu), scoring, ranking, priority classification (deterministik bila metadata cukup), LaTeX rendering, diff, penamaan file, validasi approval, metadata ekspor, dan QA deterministik.

Alasan tidak memakai LangChain/LangGraph/CrewAI: prompt dan state menjadi tersembunyi, sulit direproduksi, dan menambah token. Pipeline linear dengan checkpoint lebih mudah diuji.

---

## 4. Batas Modul

| Batas | Aturan |
|---|---|
| Frontend ↔ Backend | Hanya API JSON. Frontend tidak mengakses database atau filesystem. |
| Backend ↔ Database | Hanya melalui repository/service layer; tidak ada akses SQL tersebar di route. |
| Domain ↔ LLM | Hanya melalui `LLMClient`; domain tidak mengimpor SDK vendor. |
| Domain ↔ Provider | Hanya melalui adapter; quirk vendor tidak masuk prompt/pipeline. |
| Discovery ↔ Eligibility | Discovery menyimpan job dan versi deskripsi; eligibility menilai; discovery tidak menulis status eligibility. |
| Eligibility ↔ Scoring | Fit hanya dihitung untuk `eligible`; eligibility tidak memakai tier. |
| Scoring ↔ Ranking | Ranker hanya mengurutkan assessment; tidak mengubah skor. |
| Generation ↔ Export | Generation membuat versi; export hanya membaca versi `Approved` dan menulis file. |
| Status projector ↔ semua domain | Projector menandai `Outdated`; tidak menjalankan ulang analisis atau membuat dokumen. |
| Security ↔ semua domain | Validasi URL, redaksi, consent, sanitize dipanggil di boundary, bukan diduplikasi. |

Detail input/output per domain ada di masing-masing dokumen `docs/domains/`.

---

## 5. Aliran Data

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

Entity dan relasi lengkap ada di [`../domains/DATABASE.md`](../domains/DATABASE.md).

---

## 6. Runtime

### Produksi lokal

- Satu proses di `127.0.0.1`.
- Backend menyajikan API dan aset frontend hasil `vite build`.
- State di MySQL dan file; browser hanya view/control.
- Tugas panjang (fetch, parsing, generate, compile, ekspor) berjalan sebagai background task in-process dengan progress dan status.
- Tidak ada queue eksternal untuk v1.
- Discovery terjadwal memakai satu thread in-process (`DiscoveryScheduler`) yang memanggil `DiscoveryService.start_run` yang sama dengan tombol manual. Thread membuka koneksi sendiri, tidak berbagi koneksi request, dan default mati (`[discovery] scheduler_enabled = false`). Lock discovery yang sudah ada menjaga agar hanya satu run berjalan.

### Pengembangan

- Vite dev server di localhost, proxy API ke backend lokal.
- Tidak ada CORS terbuka ke jaringan.
- Tidak ada server frontend terpisah di produksi.

### Keamanan runtime

- Bind `127.0.0.1`; jangan `0.0.0.0`.
- Tanpa tunnel publik.
- Tanpa autentikasi multi-user; keamanan bergantung pada bind localhost, akun OS, ACL direktori, dan CSRF token.
- Detail di [`SECURITY.md`](SECURITY.md).

---

## 7. Invariant Arsitektur

1. Tidak ada request discovery sebelum profil `confirmed`.
2. `profile_version_id` tercatat pada setiap run discovery dan assessment.
3. Eligibility dinilai sebelum fit score dan sebelum dokumen dibuat.
4. Fit score tidak memuat eligibility atau priority tier.
5. Ranking utama hanya `eligible`; tier hanya tie-breaker dalam `window`.
6. Approval terikat `document_version_id` + `content_hash`.
7. Ekspor hanya dari versi `Approved`.
8. Master CV tidak pernah ditimpa.
9. Dokumen lowongan A tidak menimpa dokumen lowongan B.
10. `Outdated` tidak sama dengan `Failed`; penandaan tidak memicu regenerasi.
11. Tidak ada auto-submit atau klaim lamaran terkirim.
12. Log operasional tidak memuat isi CV/CL, prompt, respons model, atau PII.
13. Debug model I/O mati secara default.
14. Frontend tidak menghitung eligibility, fit, ranking, approval, status `Outdated`, atau nama file final.
15. Konten eksternal diperlakukan sebagai data tidak tepercaya.

---

## 8. Batas Provider-Agnostic

Pipeline hanya mengenal **role**:

| Role | Tugas | Temperatur | Model |
|---|---|---|---|
| `extract` | Ekstraksi Master CV | 0–0.2 | Dikonfigurasi; belum ditetapkan |
| `classify` | Requirement, skill mapping, klasifikasi lowongan | 0–0.2 | Dikonfigurasi; belum ditetapkan |
| `write` | CV turunan, cover letter | 0.3–0.6 | Dikonfigurasi; belum ditetapkan |
| `review` | Kritik independen | 0–0.3 | Sebaiknya berbeda dari `write` |

Kontrak konsep:

```text
generate(role, messages, response_schema, temperature, max_tokens)
  -> validated_object + metadata
```

- Satu provider aktif per konfigurasi.
- Role boleh menunjuk model berbeda pada provider yang sama.
- Tidak ada fallback lintas provider otomatis di v1.
- Structured output tidak diasumsikan native; default JSON + parse + repair maksimal 1 kali + validasi Pydantic.
- `provider`, `model`, `prompt_hash`, parameter, `response_hash`, dan `config_snapshot` disimpan untuk reproduksibilitas.

Detail di [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md).

---

## 9. Status dan State Machine

Status proses, dokumen, dan aplikasi dipisahkan. Aturan bisnis ada di [`PRODUCT.md`](PRODUCT.md) §5.7; implementasi state machine, checkpoint, dan propagasi `Outdated` ada di [`../domains/SYSTEM.md`](../domains/SYSTEM.md).

Alur dokumen: `Draft → In Review → Approved → Exported`. Edit/regenerate setelah approval membuat versi baru yang belum disetujui.

---

## 10. Graphify

- Graphify 0.9.80 adalah alat pengembangan untuk peta kode, dependensi, dan impact analysis.
- Bukan database runtime, bukan job search engine, bukan penyimpanan data kandidat.
- Dijalankan per fase, bukan saat runtime aplikasi.
- Output `graphify-out/` di-gitignore.
- Cakupan: `backend/src/`, `backend/tests/`, `docs/`, `backend/pyproject.toml`, prompt, schema, template.
- Kecualikan `data/`, `logs/`, `.venv/`, `graphify-out/`, `build/`, file job JSON, Master CV, dokumen kandidat.

Prosedur operasional dan perintah terverifikasi ada di [`../domains/GRAPHIFY.md`](../domains/GRAPHIFY.md).

Detail di `PLAN.md` §10.

---

## 11. Struktur Repo yang Direncanakan

Proposal ada di `PLAN.md` §12. Ringkas:

```text
D:\gawe\
  README.md, AGENTS.md, PLAN.md
  .gitignore
  config.example.toml
  .env.example
  frontend/
    package.json, package-lock.json, tsconfig.json, vite.config.ts, index.html
    src/{app,pages,components,features,lib,styles}
    tests/
  backend/
    pyproject.toml, uv.lock
    src/gawe/{api,services,orchestrator.py,config.py,db,master_cv,ingest,profile,
              jobs,eligibility,match,ranking,generate,review,export,status,llm,security,util,cli.py}
    tests/{unit,integration,e2e,fixtures}
  data/, profile/, logs/
  docs/{README.md,source-of-truth,domains,phases,adr}
  graphify-out/
```

`frontend/` dan `backend/` adalah dua direktori aplikasi terpisah. Frontend tidak mengimpor kode backend; backend tidak mengimpor kode frontend. Komunikasi hanya melalui API JSON. Pada produksi lokal, backend menyajikan aset hasil build `frontend/`.

Perintah frontend (`npm`, Vite, Vitest) dijalankan dari `frontend/`; perintah backend (`uv`, Python, `pytest`) dijalankan dari `backend/`. Test dan fixture backend berada di `backend/tests/`.

File khusus frontend (`package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`, `index.html`) berada di `frontend/`. File khusus Python (`pyproject.toml`, `uv.lock`) berada di `backend/`.

`config.example.toml` dan `.env.example` berada di root repository sebagai template konfigurasi (C6, diputuskan 2026-10-19). Backend membaca config dari root; tidak ada salinan kedua di `backend/`.

Struktur ini adalah target dan belum dibuat. Jangan membuat scaffold pada tugas dokumentasi.

---

## 12. Gap Dokumentasi yang Dicatat

Gap berikut ditemukan saat audit. Item yang sudah diselesaikan ditandai; sisanya **belum diselesaikan**:

1. `PLAN.md` §10.2 dan §10.4 sudah diselaraskan ke [`ARCHITECTURE.md`](ARCHITECTURE.md). Tidak lagi menjadi gap.
2. `PLAN.md` §12 sudah diselaraskan dengan struktur dokumentasi aktual: `docs/source-of-truth/`, `docs/domains/`, `docs/phases/`, dan `docs/adr/`. Tidak lagi menjadi gap.
3. `PLAN.md` §4.1 Privasi menyebut "Semua file di `D:\gawe\data`", sedangkan §9.5 dan §12 menempatkan `profile/` dan `logs/` di luar `data/`. Perlu klarifikasi saat Phase 0/1; jangan mengubah aturan privasi secara diam-diam.
4. `config.example.toml` dan `.env.example` berada di root repository sebagai template konfigurasi (C6, selesai 2026-10-19). Backend membaca config dari root. File konfigurasi frontend berada di `frontend/`; file Python berada di `backend/`.

---

## 13. Referensi PLAN.md

- §1 Executive Summary
- §5 Diagram Alur (5.1 pipeline, 5.2 komponen, 5.3 relasi data)
- §6 Arsitektur Komponen dan Agent; §6.1 batas provider-agnostic
- §7 Reviewer dan Quality Gates
- §8 Rekomendasi Technical Stack
- §9 Data Model dan Strategi Penyimpanan
- §10 Strategi Graphify
- §11 Security dan Reliability
- §12 Proposed Repository Structure
- §13 Roadmap Implementasi
