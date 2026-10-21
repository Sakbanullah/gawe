# Architecture Decision Records

**Status:** Phase 0 selesai 2026-10-19. ADR-0001 disetujui pengguna.

Direktori ini disediakan karena `PLAN.md` §12 dan §13 Phase 0 menyebut `docs/adr/`. ADR dibuat saat Phase 0, bukan pada tugas dokumentasi ini.

Aturan:

- Satu ADR per keputusan arsitektur yang perlu dijelaskan konteksnya.
- Status keputusan tetap otoritatif di [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md). ADR tidak boleh mengubah status `OPEN` menjadi final.
- ADR yang sudah ada di `PLAN.md` (misalnya D22 Mantine) boleh diringkas, tetapi harus merujuk `DECISIONS.md` dan `PLAN.md`.
- Jangan membuat ADR untuk keputusan yang belum final.
- Jangan membuat ADR kosong.
- Keputusan implementasi yang didelegasikan ke Phase 0 (misalnya routing, server-state, validasi frontend, pinning versi) boleh dicatat di ADR tanpa membuat ID `D*` baru dan tanpa mengubah status `OPEN` milik keputusan produk.

ADR yang diperkirakan dibuat di Phase 0:

| Topik | Status |
|---|---|
| Frontend stack: React + TypeScript + Vite + Mantine, Mantine-first, tanpa stylesheet utama | [ADR-0001](0001-frontend-stack.md) — Accepted |
| Kontrak API dan generate tipe dari OpenAPI | Tidak dibuat sebagai ADR terpisah. Normatif di [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md) dan [`../phase-00/contracts/openapi.yaml`](../phase-00/contracts/openapi.yaml); C4 ditutup 2026-10-19 setelah persetujuan pengguna |
| Kontrak provider-agnostic `LLMClient` | Tidak dibuat sebagai ADR terpisah. Draft di [`../phase-00/contracts/llm-client.md`](../phase-00/contracts/llm-client.md) |
| Aturan ranking fit-first dan `tie_window` | Tidak dibuat sebagai ADR terpisah. Draft di [`../phase-00/contracts/ranking.md`](../phase-00/contracts/ranking.md); keputusan produk D13 tetap otoritatif |
| Strategi penyimpanan MySQL + file + JSON | Tidak dibuat sebagai ADR terpisah. Normatif di [`../domains/DATABASE.md`](../domains/DATABASE.md); DDL final masih `OPEN` |

ADR terpisah tidak dibuat untuk empat topik terakhir karena isinya sudah normatif di kontrak atau dokumen domain. Membuat ADR duplikat akan menambah salinan yang bisa menyimpang.

## Daftar ADR

| ADR | Judul | Status |
|---|---|---|
| [0001](0001-frontend-stack.md) | Frontend stack | Accepted (Phase 0) |
