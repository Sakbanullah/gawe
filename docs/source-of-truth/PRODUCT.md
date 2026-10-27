# PRODUCT — Kebutuhan Produk dan Aturan Bisnis

**Source of Truth untuk:** kebutuhan produk, workflow, gate manusia, aturan bisnis, batas scope, definisi MVP.
**Bukan Source of Truth untuk:** status keputusan (lihat [`DECISIONS.md`](DECISIONS.md)), formula skor (lihat [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md)), kontrak API (lihat [`API-CONTRACTS.md`](API-CONTRACTS.md)).
**Referensi master:** `PLAN.md` §1, §3, §4, §13, §14, §15.3, §16.

---

## 1. Tujuan Produk

Gawe adalah **aplikasi web lokal untuk satu pengguna** yang membantu kandidat:

1. Mengubah Master CV menjadi profil kandidat terverifikasi.
2. Menemukan lowongan secara otomatis dari sumber terverifikasi; URL manual tersedia sebagai jalur kedua. Urutan prioritas sumber (D26): API resmi per perusahaan, lalu API agregator resmi, lalu URL manual, lalu jalur `browser`/ekstensi yang bersifat opsional dan paling akhir.
3. Menilai kelayakan dan kecocokan lowongan secara terpisah dan transparan.
4. Menghasilkan CV turunan dan cover letter per lowongan yang dapat ditelusuri ke fakta sumber.
5. Meninjau, menyetujui per versi, dan mengekspor PDF.
6. Membuka halaman lamaran resmi; pengguna mengirim lamaran sendiri.

Target pasar: **Indonesia dan global**.

Bukan tujuan produk: deployment publik, multi-user, auto-submit, auto-email, atau klaim bahwa lamaran sudah terkirim.

---

## 2. Pengguna dan Konteks

- Satu pengguna, satu mesin lokal, satu proses aplikasi pada satu waktu (asumsi A5).
- Browser modern di mesin lokal.
- Data kandidat adalah PII dan tidak boleh keluar ke provider cloud tanpa consent.
- Pengguna tetap pengambil keputusan akhir di setiap gate.

---

## 3. Prinsip Produk

| Prinsip | Konsekuensi |
|---|---|
| Master CV adalah satu sumber fakta | Master CV immutable; dokumen lamaran adalah turunan per lowongan |
| Profil harus dikonfirmasi sebelum pencarian | Tidak ada alur upload → scraping otomatis |
| False positive lebih mahal daripada false negative | Eligibility dievaluasi terpisah, bukan disamarkan sebagai skor |
| Fit score adalah dasar ranking | Priority tier hanya tie-breaker |
| Integritas dokumen lebih penting daripada kreativitas | Setiap klaim penting harus punya bukti atau deklarasi pengguna |
| Reviewer terisolasi | Instruksi reviewer terpisah dari proses penulisan |
| Sumber lowongan harus jujur | Discovery otomatis adalah jalur utama; seed adalah target, bukan cakupan terverifikasi; URL manual adalah jalur kedua; jalur `browser`/ekstensi opsional dan paling akhir (D26) |
| Apply adalah tindakan manusia | Tidak ada auto-submit |
| Approval melekat pada versi dokumen | Edit/regenerate membuat versi baru yang belum disetujui |
| Backend adalah sumber kebenaran | Frontend tidak menghitung aturan bisnis otoritatif |

---

## 4. Tiga Workflow

Nama `/setup`, `/scrape`, `/apply` dipertahankan sebagai nama workflow internal dan label UI. Antarmuka utama adalah halaman web, bukan slash command OpenCode.

| Workflow | Halaman | Input | Output | Gate |
|---|---|---|---|---|
| `/setup` | `/master-cv` | Master CV (PDF/DOCX/TXT/MD) + work preference | Master CV record, ekstraksi, profil draft, versi confirmed | Konfirmasi pengguna |
| `/scrape` | `/discovery` | Profil confirmed + source registry + preferensi | Job + versi deskripsi + eligibility + fit score (eligible) + ranking | Pengguna memilih job |
| `/apply` | `/applications/:id` | URL atau `job_id` + profil confirmed | Versi deskripsi, eligibility, fit assessment, CV/CL versions, findings, approval per versi, PDF + metadata ekspor | Eligibility gate + review + approve per versi; Apply manual |

### 4.1 Gate manusia

1. **Profil:** discovery tidak berjalan sebelum profil dikonfirmasi. Versi profil dicatat.
2. **Lowongan:** pengguna meninjau eligibility, fit score, alasan, dan gap sebelum memilih. `needs_review` harus diselesaikan sebelum dokumen dibuat. `ineligible` tidak masuk alur dokumen normal.
3. **Dokumen:** pengguna membandingkan CV turunan dengan Master CV, mengedit, meminta revisi, dan menyetujui versi tertentu.
4. **Final:** ekspor hanya dari versi yang disetujui. Tombol Apply membuka halaman resmi; tidak ada auto-submit atau auto-email.

### 4.2 Urutan kanonik `/apply`

1. Pilih lowongan dari Job Matches (hasil discovery otomatis) atau masukkan URL manual sebagai fallback.
2. Validasi sumber, ambil deskripsi, ekstrak requirement, simpan versi deskripsi yang dianalisis.
3. Jalankan eligibility assessment **sebelum** fit score dan sebelum dokumen dibuat.
4. Status eligibility menentukan langkah:
   - `eligible` → lanjut ke fit assessment dan pembuatan dokumen.
   - `needs_review` → dokumen diblokir sampai status diselesaikan.
   - `ineligible` → tidak ada dokumen melalui alur normal.
5. Hitung fit score untuk `eligible`, tampilkan bukti dan gap.
6. Susun **rencana penyesuaian** dokumen dari fit dan bukti yang sudah ada: bagian yang dipakai, diringkas, dihilangkan, kata kunci berbukti, dan gap yang dibiarkan. Pengguna menyetujui rencana sebelum dokumen dibuat.
7. Setelah rencana disetujui, hasilkan CV turunan dan cover letter dari Master CV.
8. Self-check backend: grounding klaim ke Master CV, gap tidak muncul sebagai klaim, panjang, dan kata kunci relevan. Dokumen yang gagal tidak bisa diajukan untuk approval.
9. Review, edit, approve per versi, ekspor.
10. Apply membuka halaman resmi; pengguna mengisi dan submit sendiri.

---

## 5. Aturan Bisnis

### 5.1 Priority tier

Tier adalah **atribut terpisah dan tie-breaker**, bukan filter dan bukan komponen fit score.

| Tier | Kategori | Arti operasional |
|---|---|---|
| P1 | Global — onsite | Peran di luar Indonesia yang membutuhkan kehadiran fisik di luar Indonesia (onsite/hybrid) |
| P2 | Global — remote | Remote yang secara eksplisit menerima kandidat dari Indonesia atau kandidat worldwide |
| P3 | Indonesia — remote | Peran berbasis Indonesia; sepenuhnya remote |
| P4 | Indonesia — onsite | Peran berbasis Indonesia; onsite/hybrid |
| `unclassified` | Metadata tidak cukup | Tidak ditebak; ditampilkan dengan alasan |

Aturan klasifikasi dan aturan D15/D16 ada di [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md). Definisi tier di sini adalah definisi bisnis yang otoritatif.

### 5.2 Eligibility

Tiga status, bukan angka:

| Status | Arti | Perlakuan produk |
|---|---|---|
| `eligible` | Semua persyaratan wajib yang dapat diverifikasi terpenuhi | Masuk ranking utama; fit dihitung; boleh lanjut ke dokumen |
| `ineligible` | Ada persyaratan wajib yang jelas tidak terpenuhi | Ditampilkan terpisah dengan alasan; tidak ada dokumen via alur normal |
| `needs_review` | Informasi tidak cukup, ambigu, atau bertentangan | Ditampilkan terpisah; bukan eligible; fit belum dihitung; dokumen diblokir |

Aturan: jangan menganggap persyaratan terpenuhi bila informasi penting tidak diketahui. Jangan membuat kesimpulan hukum atau imigrasi. Jangan menyamarkan ketidakpastian dengan skor numerik.

### 5.3 Ranking

- Daftar utama hanya `eligible`, diurutkan `fit_score` menurun.
- Tie-breaker hanya berlaku bila skor sama atau selisih ≤ `tie_window`.
- Default `tie_window = 0` (hanya skor identik).
- Urutan tie-break: tier P1 → P4 (`unclassified` terakhir), lalu `posted_at` terbaru, lalu `job_id` stabil.
- P1 dengan fit rendah tidak boleh mengalahkan P2 dengan fit tinggi di luar band.
- Pengguna dapat mengganti sort ke `priority_tier` secara eksplisit; itu bukan default dan diberi label.
- Rekomendasi (`apply_now`, `consider`, `stretch`, `needs_review`, `ineligible`) diturunkan dari eligibility + fit + gap, bukan dari tier.
- Fit score tidak memuat komponen eligibility atau priority tier.

Formula dan detail ada di [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md).

### 5.4 Approval dan ekspor

- Approval terikat pada `document_version_id` + `content_hash`.
- Approval CV dan cover letter independen.
- Edit atau regenerate setelah approval membuat versi baru berstatus belum disetujui.
- Ekspor hanya dari versi `Approved`; ekspor mencatat ID dan hash versi.
- Versi baru yang belum disetujui tidak boleh menggantikan file final yang sudah disetujui.
- Approval lama tetap tersimpan sebagai riwayat.

### 5.5 Penamaan file

```text
CV_<Candidate>_<Company>_<Position>.pdf
Cover_Letter_<Candidate>_<Company>_<Position>.pdf
```

Nama berasal dari profil confirmed dan lowongan terpilih. Nama disanitasi, dapat diedit sebelum ekspor, dan perubahan nama tidak mengubah isi atau approval. Aturan teknis ada di [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md).

### 5.6 Apply

- Tombol Apply membuka halaman lamaran resmi.
- URL hanya dari data sumber terverifikasi atau URL manual yang dimasukkan pengguna setelah validasi.
- Jangan mengarang URL. Jika URL resmi tidak tersedia, tampilkan keterbatasan.
- Tidak ada auto-submit, auto-email, auto-fill, atau klaim lamaran terkirim.

### 5.7 Status

Tiga konteks status yang tidak boleh dicampur:

| Konteks | Status |
|---|---|
| Proses/run | `Not started`, `Processing`, `Needs review`, `Failed` |
| Dokumen | `Draft`, `In Review`, `Approved`, `Exported`, `Outdated`, `Failed` |
| Aplikasi (ringkasan) | `Not started`, `Processing`, `Needs review`, `In Review`, `Approved`, `Exported`, `Failed`, `Outdated` |

Aturan:

- `Outdated` ≠ `Failed`.
- `Ready for review` bukan `Approved`.
- Status dokumen adalah sumber kebenaran; status aplikasi hanya ringkasan.
- `Exported` hanya setelah PDF berhasil dibuat dan tercatat pada versi approved.
- Perubahan profil confirmed atau versi deskripsi lowongan menandai analisis/dokumen terkait `Outdated` bila relevan.
- Penandaan `Outdated` tidak otomatis menjalankan ulang analisis atau membuat dokumen baru.

---

## 6. Definisi MVP

### MVP inti (Phase 1–3)

Workflow dari **discovery otomatis sampai ekspor**:

- Master CV terunggah.
- Profil terkonfirmasi.
- Lowongan ditemukan otomatis dari source registry (API resmi); URL manual tersedia sebagai jalur kedua.
- Lowongan dinilai eligibility dan fit-nya, lalu diurutkan fit-first.
- CV turunan + cover letter disetujui per versi.
- PDF bernama standar.
- Laporan review.
- Tombol Apply membuka halaman resmi.

Membutuhkan daftar seed (D3). Klaim cakupan Indonesia membutuhkan D17.

Kriteria penerimaan: `PLAN.md` §14 kriteria **1–36**. Kriteria 6 berlaku dengan minimal dua sumber ATS berjalan dan dedupe teruji; klaim cakupan Indonesia ditangguhkan sampai D17 tersedia.

### MVP discovery (Phase 1–4)

MVP inti ditambah:

- perluasan sumber terverifikasi, termasuk sumber Indonesia setelah D17;
- adapter tambahan dan agregator resmi dengan attribution;
- skala tampilan Job Matches untuk volume besar;
- laporan kesehatan sumber.

Kriteria: `PLAN.md` §14 kriteria **1–36**, dengan cakupan Indonesia terpenuhi setelah D17 tersedia dan sumber diverifikasi.

### Batas MVP

MVP inti selesai setelah Phase 3, dengan discovery otomatis berjalan. Acceptance penuh dan klaim cakupan Indonesia tidak boleh dilakukan sebelum D3 dan D17 tersedia.

---

## 7. Batas Scope (tidak dibangun)

- Auto-apply, auto-email, auto-fill, submit otomatis ke ATS.
- Deployment publik, cloud server, akses jarak jauh.
- Multi-user dan autentikasi multi-user.
- Scraper LinkedIn, Indeed, Jobstreet, Glints, Kalibrr, Dealls.
- OCR v1.
- Dashboard analitik dan halaman dekoratif.
- Template HTML server-side (Jinja2/HTMX) sebagai UI utama.
- Design system atau stylesheet kustom sebagai lapisan styling utama.
- Library komponen UI utama kedua atau utility-CSS framework sebagai pengganti Mantine.
- Vector database.
- Queue eksternal, microservice, Docker.
- Graphify sebagai runtime store.
- Framework agent otonom.
- Multi-provider routing.

---

## 8. Asumsi Produk

Asumsi yang memengaruhi aturan produk (detail di `PLAN.md` §2.3):

- Master CV utama berbasis teks, bukan scan.
- Kandidat bersedia mengisi relokasi dan work authorization saat setup.
- Kandidat bersedia mengirim teks ke provider LLM setelah consent.
- Satu pengguna, satu proses aplikasi pada satu waktu.
- Lowongan `/apply` adalah URL publik.
- Review manusia tetap dilakukan sebelum submit.
- Metadata lokasi sebagian lowongan tidak lengkap.
- Daftar 20 perusahaan seed belum ada.
- Sebagian sumber Indonesia membatasi akses otomatis.

---

## 9. Keputusan yang Memengaruhi Produk

Status lengkap dan gate ada di [`DECISIONS.md`](DECISIONS.md).

| ID | Pengaruh ke produk | Status |
|---|---|---|
| D1 | Ekstraksi nyata dan uji live Phase 3 | **Diputuskan** 2026-10-19 — 9Router lewat `openai_compatible`; consent tetap wajib |
| D3 | Daftar seed discovery | `OPEN` — menunggu konfirmasi daftar |
| D7 | Dukungan CV scan/OCR | `OPEN` — OCR ditunda |
| D10 | Durasi retensi | `OPEN` — semua durasi sementara |
| D17 | Sumber Indonesia terverifikasi | `OPEN` — butuh riset |
| D20 | Autentikasi lokal | `OPEN` — default tanpa auth |
| D21 | Override `ineligible` | `OPEN` — default tidak ada override |

D3 dan D17 memblokir aktivasi sumber serta klaim cakupan Indonesia di Phase 3, tetapi tidak memblokir implementasi adapter dengan fixture. D1 sudah diputuskan (9Router); consent cloud tetap wajib sebelum pengiriman data kandidat pertama. D10 tidak memblokir implementasi, tetapi durasi retensi tidak boleh dinyatakan final.

---

## 10. Acceptance Criteria

Acceptance criteria produk ada di `PLAN.md` §14 (kriteria 1–36) dan tidak diubah di dokumen ini. File fase memuat kriteria fase terkait secara verbatim. Cara verifikasi ada di [`../domains/TESTING.md`](../domains/TESTING.md).

---

## 11. Referensi PLAN.md

- §1 Executive Summary — prinsip, tier, MVP
- §3 End-to-End Workflow — gate manusia, artefak per tahap
- §4.0 — spesifikasi UI
- §4.1 — `/setup`
- §4.2 — `/scrape`, eligibility, ranking
- §4.3 — `/apply`, approval, penamaan file
- §13 Roadmap — fase dan gate
- §14 — kriteria penerimaan MVP
- §15.3 — yang sengaja tidak dibangun
- §16 — rekomendasi akhir
