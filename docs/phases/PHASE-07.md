# Phase 7 - Sumber `browser` dengan Sesi Login Pengguna

**Status:** disetujui 2026-10-25 (D23). Belum diimplementasikan. Papan pelacakan ada di §11A.
**Sumber:** `PLAN.md` §13 Phase 7, `docs/source-of-truth/DECISIONS.md` D23, `docs/domains/JOB-DISCOVERY.md` §4.6.

**Peringatan prioritas 2026-10-27 (Revisi 10, D26):** phase ini **opsional dan prioritas terakhir**. Urutan yang dikejar lebih dulu: API resmi per perusahaan, API agregator resmi (Phase 5, syarat D27), lalu URL manual. Jalur `browser` dan impor ekstensi tetap dipertahankan dan tidak dihapus; syarat keamanan D23 tidak dilonggarkan.

---

## 1. Tujuan dan Scope

Membaca lowongan dari jobboard yang menolak fetch anonim, memakai sesi login yang pengguna sendiri buat di profil Chromium lokal.

Termasuk:

- Playwright dengan profil Chromium persisten di luar repo;
- alur login manual sekali (headed) dan crawl (headless);
- adapter pertama untuk satu situs;
- `access_method = "browser"` di source registry;
- status sesi, `browser_blocked`, dan tombol login ulang di UI;
- perintah CLI `gawe browser login|status|clear`.

Di luar scope:

- auto-submit, auto-email, pengisian form lamaran;
- simpan password, tangani 2FA otomatis, login otomatis;
- rotasi proxy, penyamaran identitas browser, penyelesaian CAPTCHA;
- retry otomatis setelah blokir;
- perubahan dedupe, eligibility, fit, ranking, approval, ekspor, atau nama file.

---

## 2. Prasyarat dan Dependensi

- Phase 3 stabil (adapter, registry, dedupe, eligibility, ranking, selera approval/ekspor berjalan).
- D23 sudah diputuskan 2026-10-25.
- Persetujuan dependency: `playwright` + unduhan Chromium (~150 MB) ke direktori user, bukan repo.
- ToS situs pertama wajib dicatat di `tos_notes` sebelum sumber diaktifkan.

Tidak bergantung pada Phase 4, 5, atau 6.

---

## 3. Dokumen Wajib Dibaca

1. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md) §4.2, §6
2. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) D23
3. [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md)
4. [`../domains/JOB-DISCOVERY.md`](../domains/JOB-DISCOVERY.md) §4.6, §10, §11
5. [`../domains/BACKEND.md`](../domains/BACKEND.md)
6. [`../domains/TESTING.md`](../domains/TESTING.md)
7. [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) §4.10

---

## 4. File atau Modul yang Diharapkan Berubah

Baru:

- `backend/src/gawe/jobs/browser/__init__.py`
- `backend/src/gawe/jobs/browser/profile.py` — lokasi profil, cek sesi, hapus profil
- `backend/src/gawe/jobs/browser/session.py` — buka/tutup Chromium, deteksi login/CAPTCHA
- `backend/src/gawe/jobs/browser/crawl.py` — buka URL search, gulir, kumpulkan kartu, buka detail
- `backend/src/gawe/jobs/sources/<situs>.py` — adapter pertama, kontrak `build_url` + `parse`

Berubah:

- `backend/pyproject.toml` — dependency `playwright`
- `backend/src/gawe/jobs/sources/__init__.py` — daftar adapter `browser`
- `backend/src/gawe/jobs/sources/registry.py` — `ACCESS_METHODS` menerima `browser`
- `backend/src/gawe/services/discovery_service.py` — cabang fetch `browser`, status `browser_blocked`
- `backend/src/gawe/api/routes/sources.py` — `access_method` menerima `browser`, endpoint login/status
- `backend/src/gawe/cli.py` — `gawe browser login|status|clear`
- `frontend/src/pages/SettingsPage.tsx` — opsi sumber browser, status sesi, tombol login
- `frontend/src/app/api-types.gen.ts` — regenerasi setelah `openapi.yaml`

---

## 5. Persyaratan dan Batasan

- Profil di `%LOCALAPPDATA%\Gawe\browser-profile`, di luar repo dan DB.
- Profil tidak masuk backup, log, error message, atau respons API.
- Cookie tidak dibaca, tidak dicetak, tidak dikirim ke klien.
- Login hanya headed dan hanya dipicu pengguna. Crawl headless dengan profil yang sama.
- `robots.txt` tidak dicek untuk jalur ini; alasannya tercatat di `SECURITY.md` §4.2.
- Run berhenti pada CAPTCHA, halaman login, atau 403: status `browser_blocked`, tanpa retry otomatis.
- Sesi kedaluwarsa terdeteksi sebelum crawl: status `session_expired`, sumber di-skip.
- Batas per run (jumlah kartu, halaman detail, timeout) disimpan di registry, bukan hardcode di adapter.
- Adapter pertama hanya untuk satu situs. Situs kedua menunggu persetujuan pengguna.
- Profil **tidak** dihapus saat aplikasi ditutup (keputusan pengguna 2026-10-25). Login sekali, berlaku sampai sesi mati. Hapus hanya lewat `gawe browser clear` atau otomatis setelah `browser_blocked` terdeteksi.
- Tidak ada apply, submit, atau interaksi selain membaca halaman daftar dan detail.

---

## 6. Keamanan, Privasi, dan Error Handling

- Content Security: halaman hasil crawl adalah data tidak tepercaya, bukan instruksi.
- Nomor halaman dan URL detail divalidasi dengan guard SSRF yang sama; host dikunci ke host situs sumber.
- Ukuran HTML per halaman dibatasi; halaman melebihi batas → skip dengan alasan.
- Kill browser saat run selesai, gagal, atau timeout. Tidak ada proses yatim.
- Log hanya metadata: sumber, jumlah kartu, jumlah detail, durasi, kode error. Tidak ada teks lowongan, URL berisi token, atau cookie.
- `gawe browser clear` menghapus direktori profil dan mengembalikan status sesi ke `unknown`.

---

## 7. Acceptance Criteria

- Login manual tersimpan di profil luar repo; tidak ada kredensial di DB.
- Satu run membaca minimal 5 lowongan lengkap (judul, perusahaan, URL, deskripsi) dari satu situs.
- Lowongan hasil crawl masuk alur normal: dedupe, eligibility, fit, ranking.
- Blokir (CAPTCHA/login/403) menghentikan run tanpa retry otomatis dan menghasilkan `browser_blocked`.
- Sesi kedaluwarsa menghasilkan `session_expired` dan tidak memulai browser.
- Tidak ada cookie, password, atau path profil di log, DB, backup, atau respons API.
- Tidak ada auto-submit atau interaksi tulis ke situs.
- Alur lama tidak rusak: sumber `ats_api` dan URL manual tetap berjalan.

---

## 8. Cara Verifikasi dan Bukti

- Test unit dengan HTML tersimpan di fixture: parse kartu, parse detail, deteksi halaman login, deteksi CAPTCHA.
- Test registry: `access_method = browser` diterima dengan konfigurasi valid, ditolak tanpa URL search.
- Test run: blokir → `browser_blocked`, sesi mati → `session_expired`; keduanya tanpa network (session di-fake).
- Test kebocoran: assert tidak ada cookie/profil di payload respons dan log.
- Satu uji live terbatas pada situs pertama yang disetujui, dicatat manual di `temporary/test-results.md`.
- Regresi: `test_documents.py`, `test_documents_ai.py`, `test_export.py`, `test_sources.py`, `test_discovery.py`.
- Laporkan perintah, output, jumlah passed/failed/skipped, durasi, dan batasan.

---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak |
|---|---|
| D10 | Retensi cache job sementara; tidak memblokir implementasi |
| D11 | API berbayar; jalur ini tidak memakainya |
| D17 | Klaim cakupan Indonesia; jalur ini tidak mengklaim cakupan |

Tidak ada keputusan `OPEN` yang memblokir implementasi Phase 7.

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti bila:

- situs pertama belum disetujui atau `tos_notes` belum dicatat;
- diperlukan rotasi proxy, penyamaran identitas browser, atau penyelesaian CAPTCHA;
- dibutuhkan penyimpanan password atau penanganan 2FA otomatis;
- profil atau cookie akan tersimpan di DB, log, atau backup;
- crawl menuntut auto-submit atau interaksi tulis;
- hasilnya nol lowongan pada dua run berturut-turut setelah login valid (struktur DOM berubah).

---

## 11. Gate Persetujuan

- D23 diputuskan 2026-10-25.
- Situs pertama disetujui pengguna, dengan `tos_notes` tercatat.
- Persetujuan eksplisit pengguna sebelum situs kedua.

---

## 11A. Papan Pelacakan Eksekusi

Rencana dikerjakan per langkah. Setiap langkah berhenti dan dilaporkan sebelum langkah berikutnya dimulai. Pengguna menentukan langkah mana yang dikerjakan lebih dulu.

| Langkah | Isi | Bergantung pada | Status | Bukti |
|---|---|---|---|---|
| L1 | `playwright` + Chromium terpasang; `jobs/browser/profile.py`, `session.py`; CLI `gawe browser login\|status\|clear` | — | Selesai dengan bukti | Playwright 1.56.0 + Chromium 141.0.7390.37; `browser status` -> `no_profile` tanpa profil; headless visit `example.com` -> `ok`; `test_browser_session.py` 3 passed |
| L2 | Uji gerbang: login manual berhasil, `status` melaporkan sesi aktif, `clear` menghapus profil | L1 | Diblokir | Indeed: `Blocked - Indeed.com` (Chromium dan Chrome asli). Jobstreet: Cloudflare challenge, `<title>Just a moment...</title>`, redirect berisi `__cf_chl_rt_tk`, 6.205-6.331 byte. Kedua situs menolak browser automation. Butuh keputusan pengguna: situs lain atau hentikan Phase 7. |
| L3 | `jobs/browser/crawl.py` + `jobs/sources/indeed.py`; `registry.py` menerima `access_method = browser` | L2 (situs lolos gerbang) | Diblokir | Menunggu situs yang lolos L2. |
| L4 | `discovery_service.py` cabang `browser`; `api/routes/sources.py` login/status; UI Settings | L3 | Diganti | Jalur `browser` dihentikan (Indeed + Jobstreet menolak). Diganti jalur ekstensi: endpoint `POST /api/import/browser` + token + UI Settings, lihat baris L4e. |
| L5 | Fixture test, test blokir/sesi, test kebocoran, regresi, satu uji live | L4 | Belum dimulai | Belum ada |

Jalur ekstensi (pengganti L3-L5 untuk browser automation, disetujui pengguna 2026-10-25):

| Langkah | Isi | Bergantung pada | Status | Bukti |
|---|---|---|---|---|
| E1 | Backend `POST /api/import/browser`: token pairing, validasi host, normalisasi, job masuk `manual_url` + `enabled=0`, eligibility dijalankan | — | Selesai dengan bukti | `test_browser_import.py` 8 passed; token 401, origin web 403, host asing ditolak, batas 50, duplikat tidak dobel |
| E2 | Ekstensi Brave/Chrome: manifest, content script Jobstreet, background fetch, popup token + kirim | E1 | Selesai dengan bukti (kode) | `extension/` ditulis; mode kartu dan mode detail (deskripsi penuh); belum dimuat ulang ke Brave untuk mode detail |
| E6 | D21: tinjauan manusia `PATCH /api/matches/{job_id}/eligibility`, migrasi `0016`, panel tinjauan di drawer Matches | E1 | Selesai dengan bukti | `test_eligibility_review.py` 11 passed; frontend 27 passed; `DECISIONS.md` D21 `CLOSED` |
| E3 | Settings Gawe: token impor browser (buat baru + salin) | E1 | Selesai dengan bukti | typecheck bersih; `SettingsPage.test.tsx` 7 passed |
| E4 | Uji nyata di Brave: load unpacked, tempel token, kirim satu halaman Jobstreet | E2, E3 | Belum dimulai | Belum ada |
| E5 | Perbarui OpenAPI + `API-CONTRACTS.md` untuk endpoint baru, regenerasi `api-types.gen.ts` | E1 | Belum dimulai | Belum ada |

Catatan status yang dipakai di tabel: `Belum dimulai`, `Sedang dikerjakan`, `Selesai dengan bukti`, `Ditunda`, `Diblokir`.

### L1 - rincian

- `backend/pyproject.toml`: tambah `playwright`.
- `backend/src/gawe/jobs/browser/__init__.py`, `profile.py`, `session.py`.
- `backend/src/gawe/cli.py`: subcommand `browser login|status|clear`.
- Profil di `%LOCALAPPDATA%\Gawe\browser-profile`.
- Bukti yang harus dilaporkan: versi Playwright, hasil `playwright install`, path profil, output `gawe browser status`.

### L2 - gerbang keputusan

L2 menentukan kelanjutan. Bila Indeed langsung memblokir login atau crawl, adapter Indeed **tidak** ditulis; situs pengganti diajukan ke pengguna sebelum L3.

### L3 - rincian

- Crawl: buka URL search, gulir sampai batas kartu, ambil link detail, buka tiap detail.
- Adapter memakai kontrak yang sama: `build_url(source)` + `parse(html, source)` -> `ParsedJobs`.
- Blokir -> `browser_blocked`, sesi mati -> `session_expired`; tanpa retry otomatis.

### L4 - rincian

- Registry: `ACCESS_METHODS` menerima `browser`; wajib `search_url`; batas run per sumber.
- Endpoint: `POST /api/sources/{id}/login` (membuka browser headed), `GET /api/sources/{id}/session`.
- Frontend: opsi sumber browser, badge status sesi, tombol login ulang.
- `openapi.yaml` diperbarui dan `api-types.gen.ts` diregenerasi.

### L5 - rincian

- Test tanpa network untuk parse kartu, parse detail, deteksi login/CAPTCHA.
- Regresi: `test_sources.py`, `test_discovery.py`, `test_documents.py`, `test_export.py`.
- Uji live terbatas dicatat di `temporary/test-results.md`.

---

## 12. Referensi PLAN.md

- §13 Phase 7
- §4.2 source registry
- §15.3 Yang sengaja tidak dibangun
