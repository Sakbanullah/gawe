# SYSTEM — Lifecycle, Konfigurasi, dan Orkestrasi

**Domain:** lifecycle aplikasi lokal, konfigurasi, orchestration, workflow, state machine, integrasi antarmodul.
**Source of Truth terkait:** [`../source-of-truth/ARCHITECTURE.md`](../source-of-truth/ARCHITECTURE.md), [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md), [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md).
**Referensi master:** `PLAN.md` §4.0, §5, §6, §8, §9, §11, §12, §13.

---

## 1. Tanggung Jawab dan Batas

**Bertanggung jawab:**

- Lifecycle proses lokal: start, bind, migrasi, serve API + aset, shutdown.
- Konfigurasi aplikasi dan secrets.
- Orchestrator: urutan tahap, gate, checkpoint, resume.
- State machine status proses, dokumen, dan aplikasi.
- Integrasi antarmodul dan pemanggilan service layer.
- Background task in-process dengan progress dan status.
- Utilitas admin: `doctor`, `backup`, `restore`, `purge`.

**Tidak bertanggung jawab:**

- Perhitungan eligibility/fit/ranking (domain eligibility).
- Isi prompt dan validasi model (domain LLM).
- Skema entity detail (domain database).
- Tampilan halaman (domain frontend).

---

## 2. Fitur dan Aturan

### 2.1 Startup

1. Muat config TOML.
2. Resolve secret dari Windows Credential Manager via `keyring`.
3. Validasi config (schema).
4. Jalankan migrasi database.
5. Bind server ke `127.0.0.1` (bukan `0.0.0.0`).
6. Sajikan API dan aset frontend hasil build.
7. Siap menerima request.

Tidak ada autentikasi multi-user. Keamanan bergantung pada bind localhost, akun OS, ACL direktori, dan CSRF.

### 2.2 Mode

| Mode | Perilaku |
|---|---|
| Produksi lokal | Satu proses menyajikan API + aset `frontend/dist/` |
| Development | Vite dev server terpisah, proxy API ke backend lokal |

Tidak ada server frontend terpisah di produksi. Tidak ada CORS terbuka ke jaringan.

### 2.3 Konfigurasi

- Format TOML.
- Contoh struktur ada di `PLAN.md` §8 (`[llm]`, `[llm.providers.*]`, `[llm.roles]`, `[privacy]`).
- Nama provider dan model adalah placeholder, bukan keputusan final.
- Secret tidak disimpan di config; gunakan `api_key_ref` ke keyring.
- Config snapshot disimpan per run/aplikasi untuk reproduksibilitas.

### 2.4 Orchestration

Satu orchestrator, banyak fungsi. LLM bukan agent otonom.

Tahap `/setup`:

1. Validasi file.
2. Hash + simpan immutable.
3. Ekstraksi teks + locator.
4. Normalisasi.
5. Ekstraksi fakta (role `extract`).
6. Verifikasi bukti.
7. Validasi deterministik.
8. Coverage check.
9. Work preferences.
10. Merge + conflict detection.
11. Review pengguna.
12. Konfirmasi.
13. Aktifkan versi + audit log.

Gate: tidak ada discovery sebelum langkah 12 selesai.

Tahap `/scrape`:

1. Muat profil confirmed + preferensi + source registry.
2. Fetch per sumber (paralel maks 3, rate limit 1 req/detik/host).
3. Simpan respons + hash + metadata.
4. Normalisasi.
5. Simpan versi posting.
6. Dedupe.
7. Klasifikasi tier.
8. Parse requirement.
9. Eligibility.
10. Fit (eligible).
11. Ranking.
12. Tampilkan.
13. Pilih job → `/apply`.

Tahap `/apply`:

1. Ambil lowongan.
2. Simpan versi deskripsi.
3. Normalisasi + tier.
4. Parse requirement.
5. Eligibility gate.
6. Cabang status.
7. Fit (eligible).
8. Pilih bukti.
9. Draft terstruktur.
10. Integritas deterministik.
11. Diff.
12. Render LaTeX.
13. Compile.
14. PDF QA.
15. Reviewer.
16. Revisi maks 2 siklus.
17. Review pengguna.
18. Ekspor versi approved.
19. Apply manual.

### 2.5 Checkpoint dan Resume

- Setiap tahap menyimpan checkpoint.
- Kegagalan model/API: retry terbatas + backoff, timeout, status jelas, resume dari checkpoint.
- Tidak ada fallback lintas provider otomatis.
- Tidak ada penulisan sebagian untuk upload yang gagal validasi.

### 2.6 Background Task

- Fetch, parsing, generate, compile, ekspor berjalan sebagai background task in-process.
- Progress dan status tersedia untuk UI.
- Tidak ada queue eksternal untuk v1.
- Asumsi: satu pengguna, satu proses aplikasi pada satu waktu.

Kontrak task/progress sudah ada di [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) §4.3; kontrak disetujui 2026-10-19.

### 2.7 State Machine

Status proses:

`Not started → Processing → Needs review → ...` dan `Failed`.

Status dokumen:

`Draft → In Review → Approved → Exported`; `Outdated` dan `Failed` adalah status terpisah.

Aturan:

- `Outdated` berarti sumber berubah, bukan proses gagal.
- `Outdated` tidak otomatis menjalankan ulang analisis atau membuat dokumen.
- Status dokumen adalah sumber kebenaran; status aplikasi hanya ringkasan.
- Approval CV/CL independen.
- `Exported` hanya setelah PDF berhasil dan tercatat.

### 2.8 Utilitas Admin

| Perintah | Fungsi |
|---|---|
| `gawe doctor` | Laporkan environment, sumber API key (tanpa nilai), status dependency |
| `gawe backup --out <zip>` | Dump MySQL + file penting |
| `gawe restore <zip>` | Validasi schema version sebelum menulis |
| `gawe purge --application <id>` | Hapus workspace + row/file terkait |
| `gawe purge --all` | Konfirmasi ganda; termasuk `data/runs/` dan `logs/` |

CLI bukan antarmuka utama.

---

## 3. Input, Output, Dependensi

| Arah | Isi |
|---|---|
| Input | Config TOML, request API, file upload, perintah CLI |
| Output | Status workflow, artefak, log metadata, respons API |
| Dependensi | Config, database, filesystem, service domain, LLM gateway, security utilities |

Modul yang diharapkan: `orchestrator.py`, `config.py`, `logging.py`, `cli.py`, `services/`, `api/`.

---

## 4. Kontrak dan Schema

- Config TOML divalidasi schema.
- `config_snapshot` menyimpan provider/model mapping, prompt version, template version.
- `run_event` menyimpan workflow, stage, durasi, token, biaya, error.
- Status yang diekspos ke API mengikuti [`../source-of-truth/PRODUCT.md`](../source-of-truth/PRODUCT.md) §5.7.

Detail entity di [`DATABASE.md`](DATABASE.md).

---

## 5. Error Handling dan State

| Kondisi | Perilaku |
|---|---|
| Config invalid | Gagal start dengan pesan jelas; jangan menebak default sensitif |
| Secret tidak tersedia | `doctor` melaporkan; fitur provider gagal dengan pesan jelas |
| Migrasi gagal | Jangan serve; laporkan |
| Provider/API gagal | Retry terbatas, checkpoint, status jelas |
| Compile gagal | `tex_only`; jangan `Exported` |
| Reviewer tidak tersedia | `review_unavailable`; dokumen tidak siap |
| Upload invalid | Tidak ada penulisan sebagian; pesan spesifik |
| Task gagal | Status `Failed`; error metadata tanpa PII |

---

## 6. Keamanan dan Privasi

- Bind `127.0.0.1`; tanpa tunnel publik.
- CSRF pada request yang mengubah state.
- Secret di keyring; env hanya fallback dev.
- Log hanya metadata; tanpa isi dokumen/PII.
- Debug model I/O mati default.
- Redaksi sebelum menulis log.
- Purge menghapus artefak terkait.
- Backup tanpa secret.

Detail di [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md) dan [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md).

---

## 7. Acceptance dan Verifikasi

Mengacu `PLAN.md` §13 Phase 1 dan §14.

- Perintah backend dijalankan dari `backend/`; perintah frontend dari `frontend/`.
- `pytest` hijau; fake LLM; tidak ada network di test.
- `doctor` melaporkan environment.
- Server hanya bind localhost.
- `vite build` berhasil; typecheck lulus.
- Tidak ada kebocoran secret/PII di log test.
- Build frontend deterministik.
- Resume setelah model/API gagal (kriteria 26).
- Backup/restore berhasil; purge menghapus data terkait.

Bukti yang dilaporkan: perintah yang dijalankan, output ringkas, dan status pass/fail. Jangan mengklaim tanpa menjalankan.

---

## 8. Keputusan dan `OPEN`

| ID | Dampak |
|---|---|
| D1 | Provider nyata untuk Phase 2B/3 live |
| D6 | Instalasi Tectonic |
| D10 | Retensi log/diagnostik |
| D20 | Autentikasi lokal |
| D22 | Mantine (final) |

Tidak ada keputusan arsitektur baru yang boleh dibuat di domain ini. Lihat [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md).

---

## 9. Referensi PLAN.md

- §4.0 Interface web lokal (runtime, background task, bind)
- §5.1 Pipeline dan §5.2 Arsitektur komponen
- §6 Arsitektur komponen dan agent
- §8 Config TOML, LLM tanpa lock-in
- §9 Data model dan penyimpanan
- §11 Security dan reliability
- §12 Struktur repo (`orchestrator.py`, `config.py`, `logging.py`, `cli.py`)
- §13 Phase 1
