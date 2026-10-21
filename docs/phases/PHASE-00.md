# Phase 0 — Kontrak dan Keputusan

**Status:** selesai. Gate Phase 0 lulus 2026-10-19 setelah persetujuan eksplisit pengguna atas schema, kontrak API (C4), dan ADR-0001. Phase 1 belum dimulai.
**Sumber:** `PLAN.md` §13 Phase 0, §14, §15.4.

---

## 1. Tujuan dan Scope

Mengunci:

- schema Master CV/profil/job/eligibility/assessment/findings,
- kontrak API,
- kontrak provider (`LLMClient`),
- prompt draft,
- keputusan library UI (D22: Mantine),
- ADR frontend,
- aturan ranking,
- fixture contoh.

Tidak ada kode aplikasi pada fase ini. Komponen: dokumen desain dan kontrak.

Di luar scope: implementasi backend/frontend, instalasi dependency, database runtime, scaffold aplikasi.

---

## 2. Prasyarat dan Dependensi

- Persetujuan pengguna untuk memulai Phase 0.
- `PLAN.md` Revisi 7 sebagai master.
- Dokumentasi `docs/` ini sebagai peta konteks.
- Tidak ada keputusan terbuka yang harus dijawab sekaligus. Gate per fase dicatat; D22 sudah diputuskan.

---

## 3. Dokumen Wajib Dibaca

1. [`../README.md`](../README.md)
2. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md)
3. [`../source-of-truth/ARCHITECTURE.md`](../source-of-truth/ARCHITECTURE.md)
4. [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md)
5. [`../source-of-truth/UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md)
6. [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md)
7. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md)
8. [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md)
9. [`../domains/ELIGIBILITY-AND-SCORING.md`](../domains/ELIGIBILITY-AND-SCORING.md)
10. [`../domains/TESTING.md`](../domains/TESTING.md)

---

## 4. File atau Modul yang Diharapkan Berubah

Belum ada kode. Deliverable dokumentasi/kontrak:

| Deliverable | Lokasi yang diusulkan |
|---|---|
| ADR frontend (React + TS + Vite + Mantine, Mantine-first) | `docs/adr/` |
| ADR keputusan lain yang sudah final | `docs/adr/` |
| JSON schema Master CV/profil/job/eligibility/assessment/findings | `docs/phase-00/contracts/` (draft; lokasi final disetujui saat Phase 0) |
| Kontrak OpenAPI awal | `docs/phase-00/contracts/` (draft; lokasi final disetujui saat Phase 0) |
| Inventaris endpoint lengkap, error envelope, pagination, task/progress, CSRF | [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) §6; seluruh item wajib disetujui |
| Kontrak `LLMClient` | `docs/phase-00/contracts/` (draft) |
| Config provider contoh | `config.example.toml` dan `.env.example` di root repository sebagai template konfigurasi (C6, selesai 2026-10-19) |
| Prompt draft | `docs/phase-00/prompts/` (draft; target implementasi `backend/src/gawe/llm/prompts/`) |
| Fixture contoh | `docs/phase-00/fixtures/` (draft; target implementasi `backend/tests/fixtures/`) |
| Aturan ranking | `docs/phase-00/contracts/` + test invariant |

Pemetaan path draft ke path implementasi ada di [`../phase-00/README.md`](../phase-00/README.md).

Jangan membuat scaffold aplikasi. Jangan membuat direktori `backend/` atau `frontend/` selama Phase 0. File kode hanya boleh dibuat bila pengguna menyetujui Phase 0 deliverable yang memerlukannya.

---

## 5. Persyaratan dan Batasan

- D22 tercatat selesai: Mantine satu-satunya library komponen UI utama.
- ADR frontend mencatat aturan Mantine-first, larangan stylesheet utama, larangan library UI kedua.
- Schema dan kontrak API disetujui sebelum implementasi.
- Kontrak API dianggap disetujui hanya bila seluruh item [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) §6 sudah tertutup; item yang masih `OPEN` memblokir bagian Phase 1 yang bergantung padanya.
- Kontrak provider tidak mengasumsikan vendor/model.
- Prompt draft netral provider.
- Draft prompt, fixture, schema, dan kontrak berada di bawah `docs/phase-00/`; tidak ada direktori aplikasi pada Phase 0.
- ADR frontend [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md) mencatat React + TS + Vite + Mantine, kebijakan stylesheet, routing, server-state, validasi, dan pinning versi.
- Aturan ranking: fit-first, tier tie-breaker, `tie_window` default 0.
- Tidak ada provider final yang diasumsikan.
- Tidak mengubah keputusan `OPEN` menjadi final.
- Tidak mengubah `PLAN.md` tanpa persetujuan.

---

## 6. Keamanan, Privasi, dan Error Handling

- Kontrak harus menetapkan error envelope yang aman (tanpa PII/secret/path internal).
- Kontrak harus menetapkan CSRF untuk mutasi.
- Kontrak harus menetapkan validasi URL.
- Schema tidak boleh memaksa penyimpanan prompt/respons mentah.
- Data klasifikasi dan retensi mengikuti [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md).
- Rancangan diagnostik harus default-off.
- Rancangan consent harus terpisah dari konfirmasi profil dan approval.

---

## 7. Acceptance Criteria

Dari `PLAN.md` §13 Phase 0:

- gate keputusan per fase tercatat;
- schema dan kontrak API disetujui;
- D22 tercatat selesai dengan Mantine;
- ADR frontend disetujui;
- tidak ada provider final yang diasumsikan.

Acceptance criteria tidak diubah.

---

## 8. Cara Verifikasi dan Bukti

- Review dokumen dan ADR.
- Cek bahwa D22 tercatat selesai.
- Cek bahwa gate D1/D3/D6/D17/D21/D10 tercatat dengan fase yang benar.
- Cek bahwa kontrak API tidak mengarang endpoint di luar yang disetujui.
- Cek bahwa tidak ada provider/model final yang diasumsikan.
- Laporkan daftar deliverable dan status persetujuan.

Bukti: daftar dokumen, hasil review, dan keputusan pengguna. Tidak ada test aplikasi pada fase ini.

---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak ke Phase 0 |
|---|---|
| D22 | Sudah final; tidak memblokir |
| D1 | Tidak perlu diputuskan, tetapi harus dicatat sebagai gate Phase 2B/3 |
| D6 | Dicatat sebagai gate Phase 3 |
| D21 | Dicatat sebagai gate Phase 3 bila override diimplementasikan |
| D10 | Dicatat sebagai retensi sementara |
| D3, D17 | Dicatat sebagai gate aktivasi sumber dan acceptance discovery Phase 3 (revisi 2026-10-19: discovery otomatis masuk Phase 3) |

Phase 0 tidak boleh memaksa keputusan yang belum jatuh tempo.

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti dan minta konfirmasi bila:

- schema atau kontrak API memerlukan keputusan produk baru;
- ditemukan konflik antara `PLAN.md` dan dokumentasi;
- muncul kebutuhan mengubah acceptance criteria;
- muncul usulan mengubah `PLAN.md`;
- ada tekanan untuk mengasumsikan provider/model;
- ada tekanan untuk menambah endpoint/teknologi yang belum disetujui.

---

## 11. Gate Persetujuan

Phase 1 tidak boleh dimulai tanpa **persetujuan eksplisit pengguna** setelah Phase 0 selesai dan deliverable disetujui.

### Catatan persetujuan (2026-10-19)

Pengguna menyetujui secara eksplisit:

- seluruh schema Phase 0 di [`../phase-00/contracts/`](../phase-00/contracts/) (`*.schema.json`);
- kontrak API C4 di [`../phase-00/contracts/openapi.yaml`](../phase-00/contracts/openapi.yaml);
- ADR-0001 di [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md).

Konsekuensi: C4 ditutup; isi schema, kontrak API, dan ADR tidak diubah setelah persetujuan. Bukti verifikasi: `python tools/check-phase-00.py` (lihat §8). Persetujuan Phase 1 terpisah dan belum diberikan.

---

## 12. Referensi PLAN.md

- §13 Phase 0 — Kontrak dan keputusan
- §14 Kriteria Penerimaan MVP
- §15.4 Pertanyaan yang perlu diputuskan
- §8 Rekomendasi stack (Mantine, config)
- §12 Proposed Repository Structure (lokasi ADR dan prompt)
