# Dokumentasi Gawe

**Status:** implementasi Phase 1–3 berjalan; Phase 3 gap 3D ditutup 2026-10-21 dan acceptance-nya menunggu gate §11. Dokumen di folder ini tetap dokumen perencanaan dan source of truth.
**Sumber master:** [`PLAN.md`](../PLAN.md) Revisi 10 (27 Oktober 2026).
**Direktori proyek:** `D:\gawe`

Dokumen ini adalah pintu masuk dokumentasi. Tujuannya: memberi coding agent dan reviewer satu peta konteks yang ringkas, modular, dan tidak saling bertentangan.

---

## 1. Hierarki Source of Truth

Urutan otoritas, dari tertinggi ke terendah:

1. **`PLAN.md`** — master plan. Otoritatif untuk scope produk, roadmap, acceptance criteria, konteks lengkap, dan riwayat keputusan. Tidak diganti oleh dokumen baru.
2. **`docs/source-of-truth/*`** — aturan normatif per area. Otoritatif untuk area yang tercantum di tabel ownership. Tidak boleh menambah keputusan produk baru.
3. **`docs/domains/*`** — detail operasional per domain. Menjelaskan cara aturan diterapkan. Tidak menciptakan keputusan baru.
4. **`docs/phases/*`** — rencana eksekusi per fase. Tidak menciptakan keputusan baru dan tidak mengubah acceptance criteria.

Jika dua dokumen bertentangan, lihat [§5 Konflik](#5-protokol-konflik). Jangan menyelesaikan konflik dengan tebakan.

### Tabel ownership fakta

| Jenis fakta | File otoritatif |
|---|---|
| Kebutuhan produk, workflow, aturan bisnis, batas scope, definisi MVP | [`source-of-truth/PRODUCT.md`](source-of-truth/PRODUCT.md) |
| Arsitektur sistem, batas antarmodul, aliran data, runtime | [`source-of-truth/ARCHITECTURE.md`](source-of-truth/ARCHITECTURE.md) |
| Status keputusan (final/`OPEN`), alasan, dependensi, gate per fase | [`source-of-truth/DECISIONS.md`](source-of-truth/DECISIONS.md) |
| Klasifikasi data, consent, penyimpanan, retensi, penghapusan, backup, diagnostik | [`source-of-truth/DATA-AND-PRIVACY.md`](source-of-truth/DATA-AND-PRIVACY.md) |
| Threat model, batas kepercayaan, keamanan URL/SSRF, CSRF, secret, kontrol keamanan | [`source-of-truth/SECURITY.md`](source-of-truth/SECURITY.md) |
| Kontrak endpoint dan payload lintas frontend/backend | [`source-of-truth/API-CONTRACTS.md`](source-of-truth/API-CONTRACTS.md) |
| Keputusan UI, stack frontend, komponen, state, konsistensi desain | [`source-of-truth/UI-DESIGN.md`](source-of-truth/UI-DESIGN.md) |
| Acceptance criteria per fase | `PLAN.md` §13 dan file fase terkait; tidak diubah di dokumen lain |
| Strategi verifikasi dan bukti | [`domains/TESTING.md`](domains/TESTING.md) |

Aturan: satu fakta, satu file otoritatif. File lain merujuk, bukan menyalin ulang secara normatif.

---

## 2. Struktur Dokumentasi

```text
D:\gawe\
├── AGENTS.md                       # panduan kerja coding agent
├── PLAN.md                         # master plan Revisi 7
└── docs\
    ├── README.md                   # file ini
    ├── source-of-truth\
    │   ├── PRODUCT.md
    │   ├── ARCHITECTURE.md
    │   ├── DECISIONS.md
    │   ├── DATA-AND-PRIVACY.md
    │   ├── SECURITY.md
    │   ├── API-CONTRACTS.md
    │   └── UI-DESIGN.md
    ├── domains\
    │   ├── SYSTEM.md
    │   ├── FRONTEND.md
    │   ├── BACKEND.md
    │   ├── DATABASE.md
    │   ├── LLM-AND-PROMPTS.md
    │   ├── JOB-DISCOVERY.md
    │   ├── ELIGIBILITY-AND-SCORING.md
    │   ├── DOCUMENT-GENERATION.md
    │   ├── SECURITY-AND-PRIVACY.md
    │   ├── TESTING.md
    │   └── GRAPHIFY.md
    ├── phases\
    │   ├── README.md
    │   ├── PHASE-00.md
    │   ├── PHASE-01.md
    │   ├── PHASE-02.md
    │   ├── PHASE-03.md
    │   ├── PHASE-04.md
    │   ├── PHASE-05.md
    │   └── PHASE-06.md
    ├── phase-00\
    │   ├── README.md               # deliverable Phase 0 dan pemetaan path implementasi
    │   ├── contracts\
    │   │   ├── openapi.yaml        # kontrak API Phase 0 (disetujui 2026-10-19)
    │   │   ├── master-cv.schema.json
    │   │   ├── profile.schema.json
    │   │   ├── job.schema.json
    │   │   ├── eligibility.schema.json
    │   │   ├── fit-assessment.schema.json
    │   │   ├── findings.schema.json
    │   │   ├── llm-client.md       # draft kontrak LLMClient
    │   │   └── ranking.md          # aturan ranking fit-first
    │   ├── prompts\                # 6 prompt draft, netral provider
    │   └── fixtures\               # fixture sintetis
    └── adr\
        ├── README.md               # indeks ADR
        └── 0001-frontend-stack.md  # ADR frontend Phase 0
```

Catatan: `PLAN.md` §12 sudah diselaraskan dengan struktur dokumentasi aktual: `docs/source-of-truth/`, `docs/domains/`, `docs/phases/`, dan `docs/adr/`. `config.example.toml` dan `.env.example` berada di root repository sebagai template konfigurasi (C6, selesai 2026-10-19).

---

## 3. Urutan Membaca

Wajib untuk setiap task:

1. [`../AGENTS.md`](../AGENTS.md)
2. [`README.md`](README.md) (file ini)
3. [`source-of-truth/DECISIONS.md`](source-of-truth/DECISIONS.md)
4. File fase yang sedang dikerjakan, misalnya [`phases/PHASE-01.md`](phases/PHASE-01.md)
5. Dokumen domain yang relevan dengan task
6. Bagian tertentu `PLAN.md` hanya bila perlu detail, verifikasi, atau penyelesaian konflik

Jangan membaca seluruh `PLAN.md` secara default. Jangan mengulang pembacaan dokumen yang sudah ada di konteks tanpa alasan.

---

## 4. Peta Dokumen

### Source of Truth

| Dokumen | Isi |
|---|---|
| [PRODUCT.md](source-of-truth/PRODUCT.md) | Visi, pengguna, prinsip, workflow, gate manusia, aturan bisnis, MVP inti vs MVP discovery, batas scope |
| [ARCHITECTURE.md](source-of-truth/ARCHITECTURE.md) | Runtime lokal, komponen, batas modul, aliran data, invariant arsitektur, peran Graphify |
| [DECISIONS.md](source-of-truth/DECISIONS.md) | Registry K1–K26 dan D1–D22, status, alasan, gate per fase |
| [DATA-AND-PRIVACY.md](source-of-truth/DATA-AND-PRIVACY.md) | Klasifikasi data, lokasi simpan, consent, retensi sementara, purge, backup, diagnostik |
| [SECURITY.md](source-of-truth/SECURITY.md) | Aset, batas kepercayaan, threat model, SSRF, CSRF, secret, kontrol dan verifikasinya |
| [API-CONTRACTS.md](source-of-truth/API-CONTRACTS.md) | Prinsip kontrak JSON, route group yang diketahui, payload terdokumentasi, kontrak yang masih `OPEN` |
| [UI-DESIGN.md](source-of-truth/UI-DESIGN.md) | React + TypeScript + Vite + Mantine, halaman, komponen, state, aksesibilitas, aturan styling |

### Domain

| Dokumen | Tanggung jawab |
|---|---|
| [SYSTEM.md](domains/SYSTEM.md) | Lifecycle aplikasi lokal, config, orchestration, state machine, integrasi modul |
| [FRONTEND.md](domains/FRONTEND.md) | Halaman, komponen Mantine, state UI, konsumsi API |
| [BACKEND.md](domains/BACKEND.md) | API, validasi, service, orkestrasi, business rules, enforcement gate |
| [DATABASE.md](domains/DATABASE.md) | MySQL, migrasi, model data, relasi, transaksi, persistensi |
| [LLM-AND-PROMPTS.md](domains/LLM-AND-PROMPTS.md) | Kontrak provider, fake provider, prompt versioning, validasi output, consent, batas data |
| [JOB-DISCOVERY.md](domains/JOB-DISCOVERY.md) | Sumber lowongan, fetch, normalisasi, dedupe, verifikasi sumber, klasifikasi tier |
| [ELIGIBILITY-AND-SCORING.md](domains/ELIGIBILITY-AND-SCORING.md) | Eligibility, evidence, fit score, ranking, tie-breaker |
| [DOCUMENT-GENERATION.md](domains/DOCUMENT-GENERATION.md) | Tailoring CV/CL, versi, review, approval per versi/hash, LaTeX, PDF, ekspor |
| [SECURITY-AND-PRIVACY.md](domains/SECURITY-AND-PRIVACY.md) | Penerapan kontrol keamanan, PII, redaksi, retensi, purge, SSRF, CSRF, consent |
| [TESTING.md](domains/TESTING.md) | Strategi unit/integration/e2e, fixture, isolasi, bukti, acceptance gate |
| [GRAPHIFY.md](domains/GRAPHIFY.md) | Baseline graph dokumentasi, perintah query, prosedur pembaruan, batasan operasional |

### Catatan riset

| Dokumen | Tanggung jawab |
|---|---|
| [notes/aggregator-shortlist.md](notes/aggregator-shortlist.md) | Perbandingan kandidat API agregator (Adzuna, Jooble, Google Jobs via SerpApi/JSearch). Riset read-only, bukan keputusan; `aggregator_api` belum dapat ditulis |

### Fase

| Fase | Tema | Status rencana |
|---|---|---|
| [PHASE-00](phases/PHASE-00.md) | Kontrak dan keputusan | Selesai 2026-10-19; gate lulus |
| [PHASE-01](phases/PHASE-01.md) | Fondasi backend dan frontend | Implementasi selesai 2026-10-19; menunggu persetujuan |
| [PHASE-02](phases/PHASE-02.md) | Master CV dan `/setup` (2A/2B) | 2A selesai; consent 2B diimplementasikan; acceptance 2B belum diklaim |
| [PHASE-03](phases/PHASE-03.md) | Discovery otomatis, eligibility, `/apply` | 3A–3D terimplementasi; uji live 2026-10-21; acceptance menunggu gate §11 (review manusia + persetujuan) |
| [PHASE-04](phases/PHASE-04.md) | Perluasan sumber dan skala discovery | Belum dimulai |
| [PHASE-05](phases/PHASE-05.md) | Aggregator dan operasi | Belum dimulai |
| [PHASE-06](phases/PHASE-06.md) | Hardening opsional | Belum dimulai |

Ringkasan gate dan urutan ada di [phases/README.md](phases/README.md).

Deliverable Phase 0 (prompt, fixture, kontrak, schema) disimpan di [`phase-00/`](phase-00/README.md). File itu juga memetakan path draft ke path implementasi target.

ADR frontend Phase 0 ada di [`adr/0001-frontend-stack.md`](adr/0001-frontend-stack.md).

---

## 5. Protokol Konflik

Jika dua sumber berbeda:

1. Jangan menebak.
2. Catat kedua sumber dan kalimat yang bertentangan.
3. Tandai konflik untuk review pengguna.
4. Jangan mengubah keputusan final secara diam-diam.
5. Jangan mengubah `PLAN.md` tanpa persetujuan eksplisit pengguna.

Konflik yang sudah ditemukan saat audit dokumentasi dicatat di [DECISIONS.md](source-of-truth/DECISIONS.md) §7 dan di laporan tugas. C7 (status D1), C8 (mesin database), dan C9 (posisi discovery) diselesaikan 2026-10-19; konflik lain belum diselesaikan.

---

## 6. Konvensi

- `OPEN` berarti keputusan belum final. Jangan mengimplementasikan sebagai keputusan final.
- Keputusan final memakai ID dari `PLAN.md` (`K*`, `D*`). Jangan membuat ID keputusan baru di dokumen domain atau fase.
- Semua durasi retensi saat ini **sementara** sampai D10 disetujui.
- Referensi ke `PLAN.md` memakai nomor bagian dan nama heading, misalnya `PLAN.md §4.2 Eligibility gate`.
- Perintah frontend dijalankan dari `frontend/`; perintah backend dari `backend/`. Path test dan fixture mengikuti struktur target di `PLAN.md` §12.
- Link internal harus menunjuk file yang ada.
- Jangan mengarang endpoint, schema, dependency, atau teknologi. Jika belum ditetapkan, tulis `OPEN` dan sebut fase yang harus memutuskannya.
- Dokumentasi ditulis dalam bahasa Indonesia; identifier, path, nama API, dan error string tetap verbatim.

---

## 7. Batas Tugas Dokumentasi

Dokumen ini dan seluruh isi `docs/` tidak menyatakan bahwa:

- implementasi sudah dimulai;
- Phase 1 atau fase implementasi lain sudah selesai;
- acceptance criteria sudah terpenuhi;
- test atau build sudah dijalankan;
- provider LLM sudah dikonfigurasi pada runtime lokal;
- sumber lowongan Indonesia sudah terverifikasi.

Phase 0 selesai pada 2026-10-19. Phase 1 belum dimulai; implementasi menunggu persetujuan eksplisit pengguna.
