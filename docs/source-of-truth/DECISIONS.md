# DECISIONS — Registry Keputusan

**Source of Truth untuk:** status keputusan, alasan, dependensi, gate per fase.
**Bukan Source of Truth untuk:** detail implementasi domain (lihat `docs/domains/`), acceptance criteria (`PLAN.md` §13/§14).
**Referensi master:** `PLAN.md` §2.2 (K1–K26), §2.5 (gate keputusan), §15.4 (D1–D22).

Aturan: jangan mengubah status `OPEN` menjadi final tanpa persetujuan pengguna. Jangan membuat ID keputusan baru di dokumen lain. Jika isi dokumen ini berbeda dari `PLAN.md`, `PLAN.md` menang dan konflik harus dilaporkan, bukan ditebak.

---

## 1. Status

| Status | Arti |
|---|---|
| **Diputuskan** | Keputusan final; boleh diimplementasikan |
| **Menunggu konfirmasi** | Arah sudah ada; butuh persetujuan pengguna atau daftar final |
| **Butuh riset** | Belum ada bukti; belum boleh dianggap tersedia |
| **Terbuka** | Belum diputuskan; diputuskan pada fase yang disebut |
| **OPEN** | Ringkasan untuk keputusan yang belum final |

Keputusan `OPEN` tidak boleh diperlakukan sebagai final. Fitur yang bergantung pada keputusan `OPEN` harus berhenti di batas yang diizinkan.

---

## 2. Keputusan Final (K1–K26)

Sumber: `PLAN.md` §2.2. Ringkasan operasional:

| ID | Keputusan | Konsekuensi |
|---|---|---|
| K1 | Pasar: Indonesia dan global | Discovery, preferensi, klasifikasi, dan rekomendasi mencakup kedua pasar |
| K2 | Priority tier P1 global onsite, P2 global remote, P3 Indonesia remote, P4 Indonesia onsite | Tier adalah atribut dan tie-breaker, bukan filter dan bukan komponen fit score |
| K3 | Provider/model LLM: D1 diputuskan (9Router lewat adapter `openai_compatible`); model per role tetap konfigurasi | Arsitektur provider-agnostic; provider diganti lewat konfigurasi |
| K4 | Web lokal single-user; frontend React + TypeScript + Vite; backend API JSON | Tidak ada deployment publik, cloud, multi-user, atau template HTML server-side sebagai UI utama |
| K5 | Kandidat mengunggah CV sebagai sumber profil | Tidak ada scraping profil dari LinkedIn atau sumber eksternal |
| K6 | Graphify adalah fondasi pemetaan konteks/kode/dependensi | Dipakai saat pengembangan, bukan database runtime |
| K7 | Human-in-the-loop; tidak ada auto-submit | Semua gate review dipertahankan |
| K8 | Master CV immutable; dokumen lamaran adalah turunan per lowongan | Tailoring tidak menimpa Master CV atau dokumen lowongan lain |
| K9 | Profil hasil ekstraksi wajib direview dan dikonfirmasi sebelum scraping | Tidak ada alur upload → scraping otomatis |
| K10 | `fit_score` adalah dasar ranking; priority tier hanya tie-breaker | Urutan tidak boleh didominasi tier |
| K11 | Eligibility gate terpisah dari `fit_score` | Skor tinggi tidak menyiratkan syarat wajib terpenuhi |
| K12 | Seed awal ~20 perusahaan Indonesia dan global, dikelola lewat UI | Target awal, bukan cakupan terverifikasi |
| K13 | CV maksimal 2 halaman, satu kolom, ATS-friendly, tanpa foto default | Lihat D5 |
| K14 | Instalasi Tectonic dan dependensi diputuskan saat Phase 3 | Tidak ada instalasi pada tahap perencanaan; lihat D6 |
| K15 | Consent sebelum data kandidat dikirim ke provider cloud | Consent gate dan minimisasi data wajib |
| K16 | Bahasa CV/CL mengikuti bahasa lowongan bila memungkinkan | Lihat D19 |
| K17 | Relokasi dan work authorization ditanyakan saat setup | Ketidakpastian menjadi `needs_review` |
| K18 | Hybrid diklasifikasikan onsite | Hybrid tidak disebut remote penuh |
| K19 | Apply membuka halaman resmi; pengguna submit sendiri | Tidak ada auto-submit/auto-email/klaim terkirim; URL tidak dikarang |
| K20 | Approval terikat versi dokumen spesifik dan independen CV/CL | Edit/regenerate membuat versi baru; ekspor hanya versi approved |
| K21 | Status proses, dokumen, dan aplikasi dibedakan; `Outdated` ≠ `Failed` | UI memakai istilah konsisten |
| K22 | Nama file PDF `CV_<Candidate>_<Company>_<Position>.pdf` dan `Cover_Letter_...` | Nama disanitasi, dapat diedit, tidak mengubah isi/approval |
| K23 | Fit score hanya setelah eligibility `eligible` | `needs_review` dan `ineligible` tidak masuk ranking fit |
| K24 | Frontend React + TypeScript + Vite + Mantine, SPA lokal | Backend API JSON; tidak ada Jinja2/HTMX sebagai UI utama |
| K25 | UI memakai komponen/styling bawaan Mantine; TypeScript bahasa utama | CSS manual minimal dan terdokumentasi; tidak mencampur library UI utama |
| K26 | Backend Python sumber kebenaran workflow, validasi, persistensi | Frontend tidak menghitung ulang eligibility, fit, approval, atau status |

---

## 3. Registry Keputusan D1–D22

Sumber: `PLAN.md` §15.4. Tabel ini otoritatif untuk status operasional.

| ID | Pertanyaan | Keputusan / default | Status | Blocking? |
|---|---|---|---|---|
| D1 | Provider/model LLM apa? Cloud, lokal, atau hybrid? | **9Router** sebagai satu provider aktif, diakses lewat adapter `openai_compatible` yang sudah ada. `base_url` dan model per role (`[llm.roles]`) configurable; tidak ada model yang di-hardcode. API key dari keyring lokal (`api_key_ref`) atau environment development; tidak pernah di-commit. Fake provider dipertahankan untuk test tanpa network. Tidak ada fallback lintas provider otomatis. Detail kebijakan data upstream (D18) tetap `OPEN`. | **Diputuskan** 2026-10-19 | Tidak; consent tetap wajib sebelum pengiriman cloud pertama |
| D2 | Pasar target? | Indonesia + global | **Diputuskan** | Tidak |
| D3 | Perusahaan/board ATS mana yang jadi seed? | **Global-only disetujui pengguna 2026-10-21** untuk Phase 3: sumber global yang sudah terverifikasi di riset Phase 2B (`greenhouse`: GitLab, Stripe; `lever`: Binance; `ashby`: Linear, PostHog, Supabase) boleh dibuat dan diaktifkan lewat UI. Sumber Indonesia (Xendit/Greenhouse, Amartha/Workable, Ajaib/Workable) tetap nonaktif sampai D17 dan persetujuan ToS/atribusi. Daftar final ~20 belum ditetapkan; tidak ada klaim cakupan Indonesia. | **Diputuskan sebagian** 2026-10-21 (global); Indonesia menunggu D17 | Ya sebelum aktivasi sumber Indonesia dan sebelum acceptance Phase 4 |
| D4 | Interface? | Web lokal single-user; React + TypeScript + Vite SPA di atas API JSON | **Diputuskan** | Tidak |
| D5 | Format CV? | Maks. 2 halaman, satu kolom, ATS-friendly, tanpa foto default; bahasa mengikuti lowongan | **Diputuskan** | Tidak |
| D6 | Boleh instal Tectonic + unduh cache bundle? | **Disetujui pengguna 2026-10-21.** Tectonic 0.17.0 dipasang di `%LOCALAPPDATA%\Gawe\tectonic\tectonic.exe` (di luar repo). Mesin PDF untuk 3D adalah Tectonic + LaTeX; bundle diunduh sekali saat kompilasi pertama. Bila binary tidak ada, ekspor tercatat `tex_only` dengan error `tectonic_unavailable` dan tidak ada klaim PDF. Font `texgyretermes`/`texgyreheros` dirujuk lewat nama file OTF. | **Diputuskan** 2026-10-21 | Tidak |
| D7 | Apakah ada CV scan/gambar? | Asumsi tidak; OCR ditunda | Menunggu konfirmasi | Tidak |
| D8 | Perlu enkripsi data at-rest selain BitLocker? | BitLocker + ACL cukup untuk v1 | Menunggu konfirmasi | Tidak |
| D9 | Reviewer wajib model/provider berbeda? | Dianjurkan bila tersedia; catat bila sama | Menunggu konfirmasi | Tidak |
| D10 | Retensi cache job dan log? | Usulan sementara: job 90 hari, log 30 hari, diagnostik 7 hari. Semua durasi belum final. | Menunggu konfirmasi | Tidak; tetapi retensi tidak boleh dinyatakan final |
| D11 | Apakah Adzuna/API berbayar lain diperlukan? | Tidak untuk v1 | Menunggu konfirmasi | Tidak |
| D12 | Konfirmasi tidak ada auto-submit? | Ya | **Diputuskan** | Tidak |
| D13 | Urutan ranking default? | Fit dulu; tier tie-breaker; `tie_window` default 0 | **Diputuskan** | Tidak |
| D14 | Relokasi dan work authorization? | Ditanyakan saat setup; ditampilkan bila lowongan menyebut; `needs_review` bila tidak jelas; tanpa kesimpulan hukum | **Diputuskan** | Tidak |
| D15 | Hybrid masuk onsite atau kategori sendiri? | Onsite; tampilkan detail kehadiran | **Diputuskan** | Tidak |
| D16 | Global remote berdasarkan apa? | Hanya P2 bila sumber mendukung eligibility Indonesia/worldwide; jika tidak jelas `needs_review` | **Diputuskan** | Tidak |
| D17 | Sumber lowongan Indonesia mana yang legal dan stabil? | Utamakan sumber terverifikasi; fallback URL manual; dokumentasikan status. Batas v1: employer-hosted ATS + URL manual; tanpa klaim cakupan nasional | **Terbuka** (riset selesai 2026-10-20, keputusan belum final) | Ya sebelum klaim cakupan Indonesia di Phase 3 |
| D18 | Kebijakan data provider? | Consent sebelum cloud; minimisasi; tanpa klaim retensi/training; opsi lokal belum diverifikasi | **Diputuskan (prinsip)**; detail provider `OPEN` (butuh riset) | Ya untuk provider |
| D19 | Bahasa CV/cover letter? | Mengikuti bahasa lowongan bila memungkinkan; jika tidak, pengguna memilih | **Diputuskan** | Tidak |
| D20 | Perlu autentikasi lokal sederhana? | Tidak untuk single-user; bind localhost + CSRF | Menunggu konfirmasi | Tidak |
| D21 | Override pembuatan dokumen untuk `ineligible`? | Default tidak. Jika dipertahankan: aksi eksplisit, peringatan, alasan tercatat, status tetap `ineligible`, bukan tombol utama | Menunggu konfirmasi | Tidak untuk Phase 1–2; ya sebelum Phase 3 jika override diimplementasikan |
| D22 | Library komponen UI? | **Mantine** satu-satunya library komponen UI utama; React + TS + Vite; styling bawaan; CSS manual hanya pengecualian terdokumentasi; tidak mencampur library UI utama | **Diputuskan** | Tidak |

---

## 4. Keputusan — Detail dan Dampak

### D1 — Provider/model LLM

- **Status:** **Diputuskan** 2026-10-19.
- **Keputusan:**
  - Provider aktif: **9Router**, diakses lewat adapter `openai_compatible` yang sudah ada. Tidak ada adapter baru.
  - `base_url` adalah konfigurasi, bukan nilai hardcoded.
  - Model dipetakan per role lewat `[llm.roles]`. Tidak ada nama model yang di-hardcode di pipeline, prompt, atau kode.
  - API key dibaca dari konfigurasi lokal: `api_key_ref` ke keyring, dengan `GAWE_LLM_API_KEY` sebagai fallback development. Nilai secret tidak ditulis di config, `.env.example`, log, atau commit.
  - Fake provider dipertahankan untuk Phase 1, Phase 2A, dan seluruh test default tanpa network.
  - Satu provider aktif; tanpa fallback lintas provider otomatis.
- **Kontrak konfigurasi yang dipakai (tidak berubah):** `[llm] active_provider`, `[llm.providers.<id>] type = "openai_compatible"`, `base_url`, `api_key_ref`, `capabilities`, dan `[llm.roles]`. `base_url` diisi lewat config TOML; `GET /api/settings/provider` sudah mengembalikan `base_url`, dan `PUT /api/settings/provider` sudah menerima provider/model/role serta `api_key_ref`. Tidak ada perubahan schema atau OpenAPI untuk keputusan ini.
- **Konsekuensi:**
  - Phase 2B dan uji live Phase 3 tidak lagi terblokir D1.
  - Consent cloud (K15, D18) tetap wajib sebelum pengiriman data kandidat pertama. Consent tetap terikat provider dan model per role.
  - 9Router adalah gateway/router. Model upstream dan kebijakan retensi/training upstream tidak diketahui. D18 detail provider tetap `OPEN`; jangan mengklaim kebijakan upstream tanpa bukti.
  - D9 (model reviewer berbeda) tetap konfigurasi. Dapat dipenuhi dengan menunjuk model berbeda pada provider yang sama.
  - Keputusan ini **tidak** memberi izin memulai Phase 2. Phase 2 tetap menunggu persetujuan eksplisit.
- **Tidak memblokir:** Phase 0, Phase 1, Phase 2A.
- **Rujukan:** [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md), [`../domains/SYSTEM.md`](../domains/SYSTEM.md) §2.3, [`API-CONTRACTS.md`](API-CONTRACTS.md) §4.10, `PLAN.md` §2.5, §6.1, §8.

### D3 — Daftar seed

- **Status:** diputuskan sebagian 2026-10-21. Pengguna menyetujui **hanya sumber global** untuk Phase 3; daftar final ~20 belum ditetapkan.
- **Global yang disetujui (terverifikasi di riset Phase 2B, adapter tersedia):** GitLab (Greenhouse), Stripe (Greenhouse), Binance (Lever), Linear (Ashby), PostHog (Ashby), Supabase (Ashby).
  - Bukti fetch live 2026-10-21: GitLab 232 job, Binance 17 job, Linear 29 job dari 3 sumber yang diaktifkan.
- **Indonesia (tetap nonaktif):** Xendit (Greenhouse), Amartha (Workable), Ajaib (Workable). Menunggu D17 dan persetujuan ToS/atribusi. Workable belum punya adapter.
- **Aturan verifikasi:** `verified` hanya bila kriteria proyek terpenuhi (adapter ada, endpoint diuji, bukti fetch tersimpan).
- **Batas klaim:** daftar ini bukan cakupan lowongan Indonesia nasional dan bukan sumber yang mencakup seluruh lowongan.
- **Bukti:** [`../../temporary/research/job-sources-2026-10.md`](../../temporary/research/job-sources-2026-10.md), [`../../temporary/api-results/`](../../temporary/api-results/).
- **Dibutuhkan untuk:** aktivasi sumber Indonesia dan acceptance Phase 4.
- **Tidak memblokir:** fondasi, Master CV, dan implementasi adapter dengan fixture.
- **Rujukan:** [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md), `PLAN.md` §4.2.

### D6 — Instalasi Tectonic

- **Status:** diputuskan 2026-10-21. Pengguna menyetujui instalasi Tectonic + unduh cache bundle.
- **Implementasi:** Tectonic 0.17.0 di `%LOCALAPPDATA%\Gawe\tectonic\tectonic.exe` (di luar repo, tidak di-commit). `render.find_tectonic` memeriksa config, env `GAWE_TECTONIC`, PATH, lalu lokasi lokal. Kompilasi dibatasi 120 detik dan 2 percobaan.
- **Perilaku bila mesin tidak ada:** ekspor ditolak `503 toolchain_unavailable` sebelum task dibuat; kegagalan kompilasi saat runtime menghasilkan `tex_only`, bukan `exported`.
- **Bukti:** PDF nyata dihasilkan pada `tests/test_export.py` dan pada uji live 2026-10-21 (CV 1 halaman, CL 1 halaman; batas 2/1).
- **Rujukan:** [`../domains/DOCUMENT-GENERATION.md`](../domains/DOCUMENT-GENERATION.md), [`../phases/PHASE-03.md`](../phases/PHASE-03.md) §5.3.

### D10 — Retensi

- **Status:** menunggu konfirmasi.
- **Usulan sementara:** cache job 90 hari, log operasional 30 hari, diagnostik 7 hari.
- **Aturan:** semua durasi di dokumentasi wajib ditandai sementara. Tidak ada durasi yang boleh diklaim sebagai kebijakan final.
- **Tidak memblokir:** implementasi; memblokir pernyataan retensi final.
- **Rujukan:** [`DATA-AND-PRIVACY.md`](DATA-AND-PRIVACY.md).

### D17 — Sumber Indonesia

- **Status:** `OPEN` (riset selesai 2026-10-20; keputusan belum final).
- **Batas v1 (usulan sementara):** employer-hosted ATS yang aksesnya diizinkan, ditambah URL manual sebagai fallback opsional.
- **Temuan riset:** tidak ada API lowongan Indonesia yang publik, terdokumentasi, dan mengizinkan akses otomatis tanpa kemitraan. Jalur yang tersedia: board ATS employer Indonesia (Xendit, Amartha, Ajaib) dan URL manual.
- **Tidak dikejar untuk v1:** key Jooble, akun publisher Careerjet.
- **Batas klaim:** sumber Indonesia belum terverifikasi secara luas; cakupan nasional tidak boleh diklaim.
- **Bukti:** [`../../temporary/research/job-sources-2026-10.md`](../../temporary/research/job-sources-2026-10.md), [`../../temporary/api-results/`](../../temporary/api-results/).
- **Dibutuhkan untuk:** klaim cakupan Indonesia dan acceptance discovery penuh di Phase 3.
- **Tidak memblokir:** implementasi adapter ATS internasional dan fixture.
- **Rujukan:** [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md).

### D18 — Kebijakan data provider

- **Status:** prinsip final; detail provider `OPEN` (butuh riset).
- **Prinsip final:** consent sebelum pengiriman cloud pertama; minimisasi data; tanpa klaim retensi/training provider tanpa bukti; opsi lokal belum diverifikasi.
- **Belum final:** retensi/training/region provider tertentu, dukungan provider lokal, dan syarat pemrosesan data per provider.
- **Dibutuhkan untuk:** kebijakan data provider aktif (9Router dan model upstream), dan fitur live yang mengirim data kandidat.
- **Tidak memblokir:** Phase 0, Phase 1, Phase 2A.
- **Rujukan:** [`DATA-AND-PRIVACY.md`](DATA-AND-PRIVACY.md), [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md), `PLAN.md` §15.4 D18.

### D20 — Autentikasi lokal

- **Status:** menunggu konfirmasi.
- **Default sementara:** tanpa autentikasi; bind `127.0.0.1`, CSRF, ACL direktori.
- **Tidak memblokir:** implementasi.
- **Rujukan:** [`SECURITY.md`](SECURITY.md).

### D21 — Override `ineligible`

- **Status:** menunggu konfirmasi.
- **Default sementara:** tidak ada override; `ineligible` tidak masuk alur dokumen normal.
- **Jika dipertahankan:** aksi eksplisit terpisah, peringatan, alasan tercatat, status tetap `ineligible`, ranking tidak berubah.
- **Dibutuhkan sebelum:** implementasi override di Phase 3.
- **Rujukan:** [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md).

### D7, D8, D9, D11

| ID | Ringkasan | Dampak bila belum diputuskan |
|---|---|---|
| D7 | CV scan/OCR | Dokumen scan ditolak; OCR Phase 6 |
| D8 | Enkripsi at-rest | BitLocker + ACL dianggap cukup untuk v1 |
| D9 | Model reviewer berbeda | Independensi reviewer lebih lemah dan harus dicatat |
| D11 | API berbayar | Tidak dipakai di v1 |

---

## 5. Gate Keputusan per Fase

| Fase | Keputusan yang dibutuhkan | Catatan |
|---|---|---|
| Phase 0 | D22 sudah diputuskan; catat gate fase lain | **Lulus 2026-10-19**: schema, kontrak API (C4), dan ADR-0001 disetujui. Tidak ada provider final yang diasumsikan |
| Phase 1 | Tidak ada keputusan terbuka selain D22; C6 sudah diputuskan (root) | Fake provider cukup; D1 tidak dibutuhkan di fase ini |
| Phase 2A | Tidak ada | Fondasi, ingest, schema, UI review, fake provider |
| Phase 2B | D1 + consent | D1 sudah diputuskan 2026-10-19 (9Router via `openai_compatible`); consent cloud versioned tersedia 2026-10-19 (API + UI Settings). Acceptance 2B tetap menunggu uji live |
| Phase 3 | D1 untuk uji live; D3 untuk aktivasi sumber; D17 untuk klaim cakupan Indonesia; D6 saat instalasi Tectonic; D21 sebelum override `ineligible` | D1 diputuskan 2026-10-19; D3 global-only disetujui 2026-10-21; D6 diputuskan 2026-10-21. Phase 3 mencakup discovery otomatis. D17 dan sumber Indonesia tetap terbuka |
| Phase 4 (implementasi) | Tidak ada gate baru selain Phase 3 selesai | Perluasan sumber dan agregator |
| Phase 4 (acceptance) | D17 untuk cakupan Indonesia penuh | Acceptance tidak boleh diklaim tanpa sumber terverifikasi |
| Phase 5 | ToS/attribution per sumber | Tidak ada D baru |
| Phase 6 | Keputusan terpisah per fitur | Opsional |

Aturan tambahan:

- D3 global sudah disetujui 2026-10-21; sumber Indonesia tetap menunggu D17. D3/D17 tidak memblokir implementasi adapter dengan fixture, tetapi memblokir aktivasi sumber Indonesia dan klaim cakupan Indonesia.
- C6 sudah diputuskan: `config.example.toml` dan `.env.example` tetap di root repository.
- D1 sudah diputuskan: 9Router lewat adapter `openai_compatible`, dengan `base_url` dan model per role sebagai konfigurasi. Prasyarat provider untuk fitur live terpenuhi; consent dan D18 tetap berlaku.
- D10 tidak memblokir implementasi, tetapi retensi tetap sementara.
- D20 tidak memblokir implementasi.
- D21 hanya memblokir jika override akan diimplementasikan.

---

## 6. Keputusan yang Sering Disalahpahami

| Pernyataan | Status yang benar |
|---|---|
| "Mantine masih kandidat" | Salah. D22 final: Mantine satu-satunya library komponen UI utama |
| "React Router dan TanStack Query sudah final" | Salah. Keduanya rekomendasi, bukan keputusan D |
| "Provider lokal sudah didukung" | Salah. Belum diverifikasi. D1 memilih 9Router; provider lokal tidak diklaim |
| "9Router adalah model final" | Salah. 9Router adalah gateway/router; model per role tetap konfigurasi dan tidak di-hardcode |
| "D1 diputuskan berarti consent tidak perlu" | Salah. Consent cloud tetap wajib sebelum pengiriman data kandidat pertama |
| "D1 diputuskan berarti Phase 2 boleh dimulai" | Salah. Phase 2 tetap menunggu persetujuan eksplisit |
| "Seed 20 perusahaan sudah ada" | Salah. Target, daftar final belum ada |
| "Discovery baru ada di Phase 4" | Salah. Discovery otomatis adalah bagian Phase 3; Phase 4 memperluas sumber |
| "Retensi 90/30/7 hari final" | Salah. Sementara sampai D10 disetujui |
| "Override ineligible adalah fitur default" | Salah. D21 terbuka; default tidak ada override |
| "Phase 2 selesai tanpa D1" | Salah. Hanya 2A/fondasi yang selesai. D1 kini sudah diputuskan, tetapi Phase 2 tetap menunggu persetujuan eksplisit |
| "Acceptance discovery bisa diclaim tanpa D3/D17" | Salah. Tidak boleh |
| "URL manual adalah jalur utama discovery" | Salah. Discovery otomatis adalah jalur utama; URL manual hanya fallback |
| "Apply otomatis mengirim lamaran" | Salah. Apply membuka halaman resmi; pengguna submit |

---

## 7. Konflik dan Gap yang Dicatat

Konflik berikut ditemukan saat audit dokumentasi. Item yang sudah diselesaikan ditandai; sisanya **belum diselesaikan**. Jangan mengubah `PLAN.md` tanpa persetujuan.

| # | Konflik/gap | Sumber | Dampak | Usulan |
|---|---|---|---|---|
| C1 | Lokasi dokumen arsitektur | `PLAN.md` §10.2/§10.4 dan §12 sudah menunjuk `docs/source-of-truth/ARCHITECTURE.md` | Tidak ada konflik tersisa | Selesai pada tugas dokumentasi struktur repo; tidak mengubah keputusan |
| C2 | Lokasi data profil/log | `PLAN.md` §4.1 menyebut semua file di `data/`; §9.5/§12 menempatkan `profile/` dan `logs/` di root | Aturan privasi dan backup bisa berbeda | Pilih: (a) pindahkan `profile/` dan `logs/` ke bawah `data/`, atau (b) pertahankan root dan perjelas `PLAN.md` §4.1; jangan mengubah aturan privasi diam-diam |
| C3 | Versi Python | `PLAN.md` §2.1 mencatat Python 3.11.8; §8 menyarankan 3.12. Probe 19 Oktober 2026: hanya CPython 3.11.8 terpasang (`C:\python\python.exe`); Python 3.12 tidak ditemukan oleh uv; `uv` 0.12.23 tersedia. Belum ada `pyproject.toml`, jadi kompatibilitas dependency belum dapat diverifikasi. | Dependency mungkin tidak cocok; target versi belum final | Pilih target 3.12 via uv atau pin 3.11.8, lalu verifikasi dependency sebelum Phase 1 |
| C4 | Endpoint API | `PLAN.md` hanya menetapkan route group `/api/setup/*`, `/api/discovery/*`, `/api/applications/*` | Implementasi frontend/backend bisa menyimpang | **Selesai 2026-10-19.** Draft kontrak lengkap ada di [`API-CONTRACTS.md`](API-CONTRACTS.md) dan [`../phase-00/contracts/openapi.yaml`](../phase-00/contracts/openapi.yaml). Pengguna menyetujui kontrak pada Phase 0; C4 ditutup. Isi kontrak tidak boleh diubah tanpa persetujuan baru |
| C5 | D18 status campuran | "Diputuskan (prinsip)" tetapi detail provider butuh riset | Bisa disalahartikan sebagai final penuh | Perlakukan sebagai prinsip final + detail `OPEN`; lihat §4 D18 |
| C6 | Penempatan config contoh | `PLAN.md` §12 dan `ARCHITECTURE.md` §11 menaruh `config.example.toml` dan `.env.example` di root; kode backend berada di `backend/` | Konfigurasi backend dapat tersebar di dua lokasi | **Selesai 2026-10-19.** `config.example.toml` dan `.env.example` tetap di root repository sebagai template konfigurasi. Backend membaca config dari root; tidak ada salinan kedua di `backend/`. Lihat [`ARCHITECTURE.md`](ARCHITECTURE.md) §12 butir 4 |
| C7 | Status D1 setelah diputuskan | `DECISIONS.md` §2 (K3), §3, dan §4 menyatakan D1 **Diputuskan** 2026-10-19; `PLAN.md` §2.2 (K3), §2.5, §13, §14, §15.4, §16, [`API-CONTRACTS.md`](API-CONTRACTS.md) §4.10/§4.13, [`PRODUCT.md`](PRODUCT.md) §9, [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md) §1/§11/§12, [`../README.md`](../README.md) §5/§7, dan komentar `config.example.toml` sebelumnya menyebut D1 `OPEN` | Dokumen dapat dibaca sebagai saling bertentangan | **Selesai 2026-10-19.** Status D1 disinkronkan di seluruh referensi tersebut. Tidak ada keputusan, schema, OpenAPI, atau kontrak konfigurasi yang diubah. Phase 2 tetap menunggu persetujuan eksplisit |
| C8 | Mesin database | `PLAN.md` §2.1, §8, §9.1, §12, §13 dan beberapa dokumen domain sebelumnya menyebut SQLite ("tanpa database server", FTS5); implementasi Phase 1/2A dan dokumentasi Source of Truth memakai MySQL 8 (Laragon), bukan PostgreSQL | Tidak ada konflik tersisa | **Selesai 2026-10-19.** MySQL 8 dipakai (keputusan pengguna). Dokumentasi Source of Truth, domain, dan `PLAN.md` diselaraskan; DDL fisik MySQL disetujui selama kontrak logis tetap. Satu-satunya penyebutan SQLite yang tersisa di `PLAN.md` adalah catatan historis di §13 dengan penanda C8 |
| C9 | Posisi discovery dalam alur produk | `PLAN.md` §13 Phase 3, §14, `PRODUCT.md` §3/§6, `JOB-DISCOVERY.md` §4, dan `docs/phases/README.md` sebelumnya menempatkan URL manual sebagai jalur utama dan discovery di Phase 4; arahan pengguna menetapkan discovery otomatis sebagai jalur utama | Roadmap, definisi MVP, dan gate keputusan tidak konsisten | **Selesai 2026-10-19.** Discovery otomatis dipindahkan ke Phase 3 (milestone 3A–3D); URL manual menjadi fallback opsional; Phase 4 menjadi perluasan sumber terverifikasi. Acceptance lama dipertahankan; kriteria discovery ditambahkan per milestone. D3/D17 tetap `OPEN` dan kini memblokir aktivasi sumber serta klaim cakupan Indonesia, bukan implementasi adapter dengan fixture |

---

## 8. Referensi PLAN.md

- §2.2 Keputusan yang sudah diambil (K1–K26)
- §2.5 Keputusan yang masih terbuka (gate per fase)
- §2.6 Konflik yang belum terselesaikan
- §13 Roadmap Implementasi (gate per fase)
- §14 Kriteria Penerimaan MVP
- §15.4 Pertanyaan yang perlu diputuskan (D1–D22)
- §16 Rekomendasi Akhir (urutan keputusan)
