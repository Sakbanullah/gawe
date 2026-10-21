# Phase 3 — Discovery Otomatis, Eligibility, dan `/apply`

**Status:** Phase 3 berjalan per 2026-10-20; gap 3D ditutup 2026-10-21. **3A** selesai untuk jalur ATS: adapter Greenhouse/Lever/Ashby, registry sumber, run discovery manual, penyimpanan respons mentah + hash, rate limit, penutupan lowongan hilang, plus fallback URL manual. Adapter HTML untuk sumber registry dan run terjadwal belum ada. **3B** terimplementasi: `job_posting_version` + `content_hash`, URL kanonik, dedupe exact/lintas sumber/fuzzy, `duplicate_of`, migrasi 0006–0008; bukti live 2026-10-21. **3C** terimplementasi deterministik: priority tier, ekstraksi requirement berbasis cue, eligibility gate, fit score, ranking, `/api/matches`, koreksi tier pengguna, cursor keyset, dan pemotongan `description_text` sesuai kontrak; ekstraksi requirement via LLM belum ada (lihat §9). **3D** selesai untuk dokumen: CV/cover letter deterministik, versi + hash, diff, revisi, review deterministik dengan pemeriksaan fakta, findings, approval terikat versi + hash, LaTeX + Tectonic + QA PDF, dan ekspor approval-gated dengan unduhan PDF. Reviewer LLM terpisah (D9) belum dijalankan. Uji live 2026-10-21 memakai 3 sumber global dan 3 URL nyata (≥1 lewat URL manual). Acceptance 3A–3D **belum** ditandai lulus: menunggu gate §11, termasuk review manusia atas kualitas output. Bukti: `backend/tests/test_discovery*.py`, `test_sources.py`, `test_assessment.py`, `test_applications.py`, `test_documents.py`, `test_export.py`, `test_reviewer_seeded_defects.py`, `frontend/src/pages/MatchesPage.test.tsx`, `ApplicationsPage.test.tsx`, `temporary/test-results.md`.
**Sumber:** `PLAN.md` §13 Phase 3, §14, §4.2, §4.3.
**Perubahan arah:** discovery otomatis adalah jalur utama. URL manual tetap tersedia sebagai fallback opsional, bukan mekanisme utama.

---

## 1. Tujuan dan Scope

Phase 3 menghasilkan alur produk penuh: Master CV → profil confirmed → **discovery otomatis** → normalisasi/dedupe → eligibility → fit → ranking → dokumen lamaran → approval → ekspor.

Scope:

**3A — Discovery**
- source registry (tambah, edit, nonaktifkan, status verifikasi);
- adapter ATS resmi: Greenhouse, Lever, Ashby;
- adapter HTML halaman karier perusahaan (allowlist, `robots.txt`);
- run discovery manual dan terjadwal, status per sumber, partial success;
- penyimpanan respons mentah + hash + `fetched_at` + `source_id`;
- rate limit, timeout, size cap, penanganan 403/429;
- deteksi lowongan kedaluwarsa/tertutup.

**3B — Normalisasi, versi, dan dedupe**
- normalisasi field dan URL kanonik;
- `job_posting_version` + `content_hash`;
- dedupe exact, lintas sumber, dan fuzzy;
- `duplicate_of` tanpa penghapusan data;
- penandaan data basi dan lowongan tertutup.

**3C — Eligibility, fit, dan ranking**
- klasifikasi priority tier + alasan + confidence;
- ekstraksi requirement (deterministik + LLM);
- eligibility gate `eligible`/`needs_review`/`ineligible`;
- fit score hanya untuk `eligible`;
- ranking fit-first, tier hanya tie-breaker;
- koreksi tier oleh pengguna.

**3D — UI dan alur dokumen**
- halaman Discovery (sumber, run, progress, error, retry);
- halaman Job Matches (tabel, filter, side panel);
- pilih lowongan → Application Workspace;
- fallback URL manual;
- CV turunan + cover letter, diff vs Master CV;
- LaTeX, compile, PDF QA, reviewer loop;
- approval per versi, penamaan file, export record;
- tombol Apply ke URL resmi.

Di luar scope:

- aggregator remote/EU dengan attribution (Arbeitnow, Remotive, Jobicy, Himalayas) → Phase 5;
- perluasan sumber Indonesia dan skala tabel lanjutan → Phase 4;
- Playwright, OCR, sumber tambahan yang belum terverifikasi → Phase 6;
- auto-submit, auto-email;
- override `ineligible` (D21 tetap `OPEN`).

---

## 2. Prasyarat dan Dependensi

- Phase 2B selesai, atau batasannya disetujui pengguna. Phase 2B live acceptance tetap **PENDING**; Phase 3 tidak boleh mengklaimnya.
- D1 sudah diputuskan (9Router via `openai_compatible`); model per role tetap konfigurasi.
- **D3** (daftar seed) dibutuhkan agar sumber dapat diaktifkan dan acceptance discovery dapat diklaim.
- **D17** (sumber Indonesia terverifikasi) dibutuhkan untuk klaim cakupan Indonesia.
- D6 dibutuhkan saat instalasi Tectonic dimulai (3D).
- D21 hanya jika override `ineligible` diimplementasikan.
- D10 tetap sementara; retensi cache job belum final.

Urutan build: 3A → 3B → 3C → 3D. Setiap milestone dapat diuji sendiri.

**Batas tanpa D3/D17:** 3A–3C boleh dibangun dan diuji dengan respons fixture tersimpan dan sumber internasional yang sudah diverifikasi dokumentasinya. Cakupan Indonesia dan acceptance discovery **tidak boleh diklaim** sebelum D3 dan D17 tersedia.

---

## 3. Dokumen Wajib Dibaca

1. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md)
2. [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md)
3. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md)
4. [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md)
5. [`../source-of-truth/UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md)
6. [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md) (sumber, akses, normalisasi, dedupe)
7. [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md)
8. [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md)
9. [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md)
10. [`../domains/BACKEND.md`](../domains/BACKEND.md)
11. [`../domains/FRONTEND.md`](../domains/FRONTEND.md)
12. [`../domains/DATABASE.md`](../domains/DATABASE.md)
13. [`../domains/TESTING.md`](../domains/TESTING.md)

---

## 4. File atau Modul yang Diharapkan Berubah

```text
backend/src/gawe/jobs/sources/{registry.py,greenhouse.py,lever.py,ashby.py,html.py,manual.py}
backend/src/gawe/jobs/{fetch.py,normalize.py,dedupe.py,priority.py,requirements.py,expiry.py}
backend/src/gawe/services/discovery_service.py
backend/src/gawe/eligibility/{evaluate.py,rules.py,explain.py}
backend/src/gawe/match/{score.py,explain.py,skills.yaml}
backend/src/gawe/ranking/{rank.py,tiebreak.py}
backend/src/gawe/generate/{plan_cv.py,plan_cover_letter.py,diff.py,render.py}
backend/src/gawe/generate/templates/{cv.tex.j2,cover_letter.tex.j2}
backend/src/gawe/review/{deterministic.py,llm_review.py,findings.py}
backend/src/gawe/export/{naming.py,export.py,manifest.py}
backend/src/gawe/status/projector.py
backend/src/gawe/api/routes/{sources.py,discovery.py,matches.py,applications.py}
frontend/src/pages/{DiscoveryPage.tsx,MatchesPage.tsx,ApplicationWorkspacePage.tsx,ApplicationsPage.tsx}
frontend/src/components/{SourceStatusList.tsx,JobMatchesTable.tsx,JobDetailDrawer.tsx,DocumentDiffView.tsx,ApprovalPanel.tsx,ExportPanel.tsx}
backend/tests/fixtures/{jobs,sources,seeded_defects}
```

Lokasi mengikuti proposal `PLAN.md` §12.

Catatan 2026-10-20: `JobMatchesTable.tsx` memuat tabel + `JobDetailDrawer` di satu modul, agar side panel dan tabel memakai tipe yang sama. `ApplicationWorkspacePage.tsx` ada pada 3D sebagai baca-saja (job, eligibility, fit, nama file, Apply, analisis ulang). Belum ada `DocumentDiffView.tsx`, `ApprovalPanel.tsx`, `ExportPanel.tsx`, `generate/*`, `review/*`, `status/projector.py`, atau `export/{export.py,manifest.py}`; `export/naming.py` sudah ada.

---

## 5. Persyaratan dan Batasan

### 5.1 Preflight

1. Profil aktif `confirmed`; `profile_version_id` dicatat pada setiap run discovery dan assessment.
2. Tanpa profil confirmed, tidak ada fetch; UI hanya menampilkan status dan tautan ke setup.
3. Sumber harus terdaftar di registry dan `enabled`; sumber `unverified`/`restricted` tidak di-fetch.
4. URL manual (fallback) divalidasi: HTTPS, host publik, bukan private/loopback/link-local, tanpa kredensial.
5. Fetch: timeout 20 detik, maks 5 redirect, maks 5 MB.
6. 403/CAPTCHA/login → berhenti untuk sumber itu; tanpa bypass. Untuk URL manual, minta pengguna menempelkan teks.
7. Data minimal (judul, perusahaan, deskripsi) tidak lengkap → jangan analisis sebagai lengkap; tandai `incomplete`.

### 5.2 Pipeline discovery

1. Muat profil confirmed + preferensi + registry `enabled`.
2. Jalankan adapter per sumber; paralel maks 3; rate limit 1 request/detik/host.
3. Simpan respons mentah + hash + `fetched_at` + `source_id` + `verification_status` saat itu.
4. Normalisasi field: judul, perusahaan, lokasi, remote, tipe kerja, seniority, gaji, tanggal, deskripsi, URL kanonik.
5. Simpan `job_posting_version` + `content_hash`; versi lama tidak ditimpa.
6. Dedupe; simpan `duplicate_of`.
7. Tandai lowongan tertutup/kedaluwarsa.
8. Klasifikasi priority tier + alasan + confidence.
9. Ekstrak requirement (pre-pass deterministik + LLM).
10. Eligibility gate per lowongan.
11. Fit score hanya untuk `eligible`.
12. Ranking fit-first; tier hanya tie-breaker.
13. Tampilkan daftar + alasan + gap + bukti; `needs_review` dan `ineligible` terpisah.

### 5.3 Pipeline dokumen (3D)

1. Pilih job dari Job Matches atau masukkan URL manual.
2. Simpan versi deskripsi yang dianalisis.
3. Eligibility → cabang status.
4. Fit score hanya `eligible`.
5. Pilih bukti.
6. Draft JSON.
7. Integritas deterministik.
8. Diff vs Master CV.
9. Render LaTeX.
10. Compile Tectonic, timeout 120 detik.
11. PDF QA.
12. Reviewer; revisi maks 2 siklus.
13. Review pengguna.
14. Ekspor versi approved.
15. Apply manual.

### 5.4 Aturan yang tidak boleh dilanggar

- Master CV immutable; dokumen lamaran turunan per lowongan.
- Tidak ada discovery sebelum profil `confirmed`.
- Eligibility sebelum fit dan sebelum dokumen.
- `needs_review` memblokir pembuatan dokumen.
- `ineligible` tidak masuk alur dokumen normal.
- Fit score tidak memuat eligibility atau priority tier.
- Ranking fit-first; tier hanya tie-breaker dalam `tie_window`.
- Approval terikat `document_version_id` + `content_hash`; CV dan CL independen.
- Ekspor hanya versi `Approved`.
- Apply membuka halaman resmi; tanpa submit/email otomatis.
- URL lamaran tidak dikarang.
- `Outdated` ≠ `Failed`.
- Backend sumber kebenaran; frontend tidak menghitung eligibility, fit, ranking, approval, status, atau nama file.
- Setiap job menyimpan `source_id` dan URL asli lowongan (`canonical_url`); tidak ada job tanpa sumber.

### 5.5 Sumber

Daftar sumber, batas akses, dan status verifikasi ada di [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md) §4. Hanya sumber dengan dokumentasi resmi yang boleh diimplementasikan.

Aturan tambahan:

- ATS API bersifat per-perusahaan; tidak ada pencarian lintas perusahaan.
- Cakupan Indonesia tidak boleh diklaim tanpa verifikasi per sumber (D17).
- Aggregator dengan syarat attribution tidak dipakai di Phase 3.
- Sumber tanpa API resmi tidak di-scrape; gunakan URL manual.

---

## 6. Keamanan, Privasi, dan Error Handling

- URL guard + validasi setiap redirect; host adapter dibatasi allowlist.
- Tanpa bypass CAPTCHA/login/paywall; tanpa rotasi proxy.
- `robots.txt` dicek untuk fetch HTML umum.
- Konten lowongan = data tidak tepercaya; sanitasi HTML; React merender teks; prompt injection dicek.
- Log tanpa isi CV/CL, prompt, respons model, atau PII; hanya metadata (`run_id`, stage, status, durasi, provider/model, hash, token, kode error).
- Debug model I/O mati secara default.
- Satu sumber gagal → hasil sukses tetap disimpan; status per sumber; retry tersedia.
- 403/429 → berhenti untuk sumber itu; laporkan.
- Lowongan tertutup/kedaluwarsa → tandai `closed`/`expired`; jangan hapus; jangan hitung sebagai kegagalan sumber.
- Data >7 hari → warning; tidak dihapus otomatis (retensi D10 belum final).
- Compile gagal → simpan `.tex` + log, retry maks 2, lalu `tex_only`; jangan `Exported`.
- Reviewer gagal → `review_unavailable`.
- Ekspor versi salah → tolak.
- Nama file ilegal/tabrakan → sanitasi/suffix stabil.

---

## 7. Acceptance Criteria

Acceptance lama tetap berlaku. Kriteria baru ditambahkan per milestone.

### 7.1 3A — Discovery

- Minimal 2 adapter ATS berjalan terhadap fixture respons tersimpan dan lulus validasi schema.
- Registry: sumber dapat ditambah, diedit, dinonaktifkan; status verifikasi dan `last_checked_at` terlihat.
- Sumber `unverified`/`restricted`/nonaktif tidak di-fetch.
- Tanpa profil confirmed, 0 request discovery.
- `profile_version_id` tercatat pada setiap run.
- Rate limit 1 request/detik/host dan paralel maks 3 dipatuhi.
- 403/429 pada satu sumber tidak menghentikan sumber lain; status `partial`/`failed` terlihat.
- Setiap job menyimpan `source_id`, `canonical_url`, `fetched_at`, dan hash respons mentah.
- 0 job tanpa sumber; tidak ada data lowongan yang direkonstruksi saat fetch gagal.

### 7.2 3B — Normalisasi dan dedupe

- `job_posting_version` dibuat dengan `content_hash`; perubahan konten membuat versi baru tanpa menimpa versi lama.
- URL kanonik membuang `utm_*`, `gh_src`, `ref`, dan trailing slash; URL final setelah redirect disimpan.
- Dedupe exact `(source, source_job_id)` dan `canonical_url` lulus.
- Dedupe lintas sumber (fingerprint) dan fuzzy 0.92 dalam blok company/location lulus pada fixture.
- Fixture dengan duplikat dikenal menghasilkan 0 duplikat ganda di tampilan; `duplicate_of` tersimpan; tidak ada data dihapus.
- Run ulang idempoten: data identik tidak menambah job baru.
- Lowongan tertutup ditandai `closed`/`expired` dan tetap tersimpan.
- Greenhouse `content` di-unescape dua kali.

### 7.3 3C — Eligibility, fit, ranking

- Setiap job punya `eligible`/`ineligible`/`needs_review` dengan alasan dan bukti.
- `needs_review` tidak diperlakukan sebagai eligible.
- Fit score hanya ada untuk `eligible`; `needs_review` dan `ineligible` tidak punya fit score.
- Urutan utama hanya `eligible`, `fit_score` menurun.
- Tier hanya tie-breaker dalam `tie_window`; mengubah tier tidak mengubah `fit_score`.
- P1 fit rendah tidak mengalahkan P2 fit tinggi.
- Filter/sort tidak mengubah skor tersimpan.
- Koreksi tier pengguna tersimpan dan dipakai pada ranking berikutnya.

### 7.4 3D — UI dan dokumen

- Halaman Discovery punya state loading, empty, error, partial success, dan retry; progress dan waktu fetch per sumber terlihat.
- Job Matches menampilkan tabel + side panel; `needs_review` dan `ineligible` terpisah.
- Pilih job membuka Application Workspace dengan job dan versi deskripsi yang benar.
- Fallback URL manual berfungsi end-to-end saat registry kosong atau seluruh sumber gagal.
- 3 URL nyata end-to-end (dari discovery; minimal 1 lewat URL manual).
- PDF CV ≤2 halaman; CL 1 halaman.
- 0 klaim tanpa bukti.
- Reviewer menangkap semua seeded defects.
- Eligibility dan fit tampil terpisah.
- `needs_review` memblokir dokumen; `ineligible` tidak menghasilkan dokumen normal.
- Approval per versi independen; ekspor hanya versi approved.
- Nama file sesuai format; diff Master CV terlihat.
- Apply membuka URL resmi tanpa submit.
- UI menandai versi baru yang belum disetujui.

### 7.5 Klaim yang tidak boleh dibuat

- Cakupan Indonesia **tidak boleh diklaim** sebelum D17 tersedia dan sumber diuji.
- Acceptance discovery tidak boleh diklaim sebelum D3 dan D17 tersedia.
- Phase 2B live acceptance tidak boleh diklaim oleh Phase 3.

---

## 8. Cara Verifikasi dan Bukti

- Contract test adapter dengan respons fixture tersimpan (tanpa network).
- Test registry: tambah/edit/nonaktifkan, status verifikasi, gate profil.
- Test rate limit, timeout, size cap, redirect, 403/429.
- Test normalisasi + URL kanonik + versi + `content_hash`.
- Test dedupe exact/lintas sumber/fuzzy; test idempotensi run ulang.
- Test penandaan `closed`/`expired`.
- Test eligibility gate dan cabang status.
- Test invariant ranking (tukar tier, filter/sort).
- Test komponen Discovery/Matches/approval/export.
- Test seeded defects untuk reviewer.
- Test approval independence dan hash.
- Test nama file + sanitasi.
- Test Apply URL tanpa submit.
- Uji live terbatas hanya pada sumber yang disetujui; tanpa data kandidat nyata di log.
- Laporkan perintah, output ringkas, pass/fail, dan batasan.

### 8.1 Bukti terakhir (2026-10-21, setelah gap 3D ditutup)

Perintah: `backend\.venv\Scripts\python.exe -m pytest backend/tests -o addopts="" -q -p no:warnings`

Output ringkas: `334 passed, 1 skipped in 67.68s` (skip = `tests/test_live_9router.py`, opt-in live provider). Bukti lengkap: `temporary/test-results.md`.

Perintah: `cd frontend; npx vitest run`, `npx tsc --noEmit`, `npm run build`

Output ringkas: `Test Files 7 passed (7)`, `Tests 41 passed (41)`; typecheck tanpa error; build sukses (`999 modules transformed`, `built in 1.24s`), hanya peringatan ukuran chunk >500 kB.

Uji live (network nyata, tanpa mock): `backend\.venv\Scripts\python.exe temporary\live_phase3.py`

Output ringkas (`failures: 0`, log `temporary/live-phase3-run.log`):

- Discovery: 3 sumber global aktif (GitLab/Greenhouse, Binance/Lever, Linear/Ashby) → 232 + 17 + 29 job diterima; 259 job dinilai: 116 `eligible`, 125 `needs_review`, 18 `ineligible`.
- 3 URL nyata end-to-end: `job-boards.greenhouse.io/gitlab/jobs/8877428002`, `jobs.ashbyhq.com/linear/0c7c2e26-...`, dan URL manual `stripe.com/jobs/search?gh_jid=8172503` (sumber sintetis `manual_url`, job Stripe "Abuse Research Engineer" terbentuk dengan eligibility `needs_review`).
- Dua workspace discovery melewati draft → review → approval → ekspor: CV 1 halaman (batas 2), CL 1 halaman (batas 1), PDF nyata (16.3 KB / 11.8 KB), nama file `CV_Ayu_Pratama_<Company>_<Title>.pdf`.
- Manual URL: dokumen diblokir karena eligibility `needs_review` — perilaku produk yang benar, bukan kegagalan.

Cakupan otomatis (tanpa network):

- `tests/test_discovery_dedupe.py` — normalisasi, URL kanonik, `content_hash`, versi baru, dedupe exact/lintas sumber/fuzzy, `duplicate_of`, penandaan `closed`.
- `tests/test_assessment.py` — klasifikasi tier (D15/D16), ekstraksi requirement must/nice + constraint `min_years`, eligibility per kategori dengan kutipan lowongan + `evidence_refs`, `needs_review` tanpa must-have, fit hanya untuk `eligible`, formula dan pembulatan half-up, ranking fit-first + tie-breaker `tie_window`, idempotensi assessment/ranking, `/api/matches` list/detail, count `/api/overview` dari assessment, cursor keyset (paging + cursor invalid/asing), batas `description_text` 262144 byte + `description_truncated`, bentuk `job_detail` sesuai kontrak, koreksi tier (simpan, hapus, validasi, CSRF, 404, ranking run tidak berubah), dan kegagalan assessment yang tampil sebagai `partial` + `assessment_failed`.
- `tests/test_applications.py` — Application Workspace: gate profil confirmed, `POST /api/applications` idempoten per `job_id` (201 lalu 200 `deduplicated`), daftar workspace + filter `status`, cursor keyset (cursor invalid ditolak), workspace memuat job + `job_posting_version_id` + eligibility + fit + nama file saran, `application_id` muncul di `/api/matches`, `needs_review` tanpa fit (`409 fit_not_available`), endpoint job/eligibility, 404 workspace asing, analisis ulang eksplisit lewat task `analysis` tanpa mengubah skor fit, `409 task_already_running` dengan `active_task_id`, CSRF pada analisis ulang, serta fallback URL manual: workspace dibuat dari halaman HTML nyata/fixture, penolakan non-HTTPS (`url_rejected`), dan penghormatan robots.txt (`robots_disallowed`).
- `tests/test_documents.py` — dokumen deterministik: draft CV/CL dari profil + job, hash canonical, diff Master CV/versi induk, gate eligibility (`needs_review`, `ineligible`, `status_outdated`), revisi + hash stale, review deterministik (evidence wajib, evidence tidak dikenal, ditambah pemeriksaan fakta terhadap profil), findings, approval terikat `document_version_id` + `content_hash`, replay idempoten, versi baru tidak mewarisi approval, data wajib, review versi approved ditolak, regenerate, CSRF, pagination, dan path edit invalid.
- `tests/test_reviewer_seeded_defects.py` — reviewer menangkap **11/11** seeded defect pada `docs/phase-00/fixtures/seeded_defects/cv_seeded_defects.md` dengan severity dan kategori yang diharapkan; tidak menghasilkan temuan pada teks yang setia pada profil; batas halaman dilaporkan sebagai temuan `format`.
- `tests/test_export.py` — ekspor hanya versi approved; `export_not_ready`, `approval_hash_mismatch`, `validation_failed` untuk `kind` salah, 404 versi asing; `503 toolchain_unavailable` sebelum task dibuat; kompilasi gagal → `tex_only`; QA gagal → `failed` (tidak pernah `exported`); versi revisi tidak mewarisi approval; PDF nyata ≤2 halaman untuk CV dan 1 halaman untuk CL; preview PDF tidak membuat export record; CSRF wajib.
- `tests/test_db.py` — migrasi `0010_applications`, `0011_documents`, dan `0012_export` diterapkan dan idempoten.
- `frontend/src/pages/MatchesPage.test.tsx` — gate profil, tabel ranking, filter eligibility, paging cursor, side panel + koreksi tier, empty state.
- `frontend/src/pages/ApplicationsPage.test.tsx` — daftar workspace, empty state, pembuatan workspace dari URL manual, workspace menampilkan eligibility/fit/nama file/Apply, blokir dokumen saat `needs_review`, analisis ulang eksplisit, generate dokumen, tabel versi + diff, review, approval, aksi ekspor khusus versi approved + tautan PDF final, dan penandaan informasi yang belum tersedia.
- `frontend/src/pages/DiscoveryPage.test.tsx` — status per sumber, retry, data tidak lengkap, dan peringatan `assessment_failed`.

Batasan: tidak ada uji UI manual; tidak ada data kandidat nyata di log; kualitas isi draft belum direview manusia; sumber Indonesia belum aktif; `D9` (reviewer model terpisah) belum dijalankan. Acceptance 3A–3D belum ditandai lulus sampai pengguna menyetujui gate §11.

### 8.2 Gap 3D yang masih terbuka (per 2026-10-21)

- Reviewer LLM terisolasi belum ada (D9 belum dijalankan). Review deterministik kini mencakup data wajib, evidence pada klaim, resolusi `evidence_index`, serta pemeriksaan fakta terhadap profil (tanggal, angka berskala, jabatan, sertifikasi, kewarganegaraan, kosakata berlebihan) dan aturan ATS/halaman.
- `status/projector.py` belum ada; proyeksi status tetap di `ApplicationService` dan `DocumentService`.
- Retensi dokumen mengikuti D10 yang masih `OPEN`; semua durasi tetap sementara.
- Kualitas isi draft belum diuji dengan reviewer manusia; tailoring deterministik hanya memilih dan mengurutkan fakta yang ada.
- Adapter `html` untuk sumber registry dan run discovery terjadwal belum diimplementasikan (di luar §7.1; jalur manual URL sudah ada).
- Sumber Indonesia belum aktif (D17 + ToS/atribusi).


---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak |
|---|---|
| D3 | Daftar seed; memblokir aktivasi sumber dan acceptance discovery |
| D17 | Sumber Indonesia; memblokir klaim cakupan Indonesia |
| D6 | **Diputuskan 2026-10-21**: Tectonic dipasang; PDF tersedia |
| D1 | Sudah diputuskan; memblokir uji live bila provider belum dikonfigurasi |
| D21 | Memblokir implementasi override `ineligible` |
| D9 | Independensi reviewer |
| D10 | Retensi cache job/log/diagnostik |

Catatan: Phase 3 kini membutuhkan discovery. D3 global disetujui 2026-10-21; D17 tetap memblokir aktivasi sumber Indonesia dan acceptance penuh Phase 4.

Catatan 3C/3D (2026-10-20): koreksi tier pengguna kini punya endpoint `PATCH /api/matches/{job_id}/tier` (kontrak di `API-CONTRACTS.md` §2.4/§4.8 dan `openapi.yaml`). Koreksi disimpan per job, tidak mengubah fit atau ranking run tersimpan, dan dipakai pada ranking berikutnya. Endpoint diuji lewat `tests/test_assessment.py` dan `MatchesPage.test.tsx`.

Catatan 3D (2026-10-21): dokumen deterministik ditambahkan: migrasi `0011_documents` (`document_version`, `document_approval`), `documents/draft.py` (CV/CL dari `profile_version.content`, hash canonical JSON, diff), `documents/review.py` (review integritas deterministik), `services/document_service.py`, dan `/api/applications/{id}/documents*` (list, generate, detail, revisi, regenerate, review, findings, approval). Approval terikat `document_version_id` + `content_hash`, menolak data wajib yang belum lengkap dan eligibility non-`eligible`, serta tidak mewarisi approval ke versi baru. Frontend menampilkan versi, isi, diff, findings, review, approval, dan edit ringkasan.

Catatan 3D gap-closing (2026-10-21): fallback URL manual diimplementasikan (`jobs/sources/manual.py`, `jobs/robots.py`, `fetch_document`, `DiscoveryService.ingest_manual_url`, sumber sintetis `manual_url` yang dibuat lazily); LaTeX + Tectonic + QA PDF ditambahkan (`documents/render.py`); ekspor approval-gated ditambahkan (`services/export_service.py`, migrasi `0012_export`, `/api/applications/{id}/exports`); preview PDF tersedia di `/documents/{id}/pdf`; reviewer deterministik diperluas dengan pemeriksaan fakta terhadap profil (`documents/factcheck.py`). Frontend menambahkan input URL manual dan aksi preview/ekspor PDF. Sumber sintetis `manual_url` tidak muncul di registry dan tidak dapat diubah pengguna.

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti bila:

- D3 belum ada dan sumber akan diaktifkan untuk acceptance;
- D17 belum ada tetapi cakupan Indonesia akan diklaim;
- sumber yang akan dipakai tidak punya dokumentasi akses resmi;
- ToS/robots melarang akses otomatis;
- rate limit tidak dapat dipatuhi;
- D21 belum diputuskan tetapi override diminta;
- acceptance criteria tidak dapat dipenuhi;
- reviewer tidak menangkap seeded defects setelah 2 siklus;
- PDF tidak dapat diproduksi dan alternatif diperlukan;
- muncul kebutuhan mengubah aturan approval/ekspor;
- ada kebocoran PII/secret.

---

## 11. Gate Persetujuan

Phase 4 tidak boleh dimulai tanpa:

- setiap milestone 3A–3D lulus acceptance-nya masing-masing;
- human review menyetujui kualitas output;
- daftar keputusan `OPEN` yang tersisa dilaporkan;
- persetujuan eksplisit pengguna.

---

## 12. Referensi PLAN.md

- §4.2 `/scrape` (prasyarat, preferensi, registry, pipeline, normalisasi, dedupe, tier, etika)
- §4.3 `/apply` (alur, preflight, pipeline, override, approval, penamaan, format, bundle)
- §7 Reviewer dan Quality Gates
- §11.2 Validasi per tahap
- §13 Phase 3 dan Phase 4
- §14 kriteria 1–36
- §15.4 D1, D3, D6, D9, D10, D17, D21
