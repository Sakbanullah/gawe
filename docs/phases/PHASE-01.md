# Phase 1 — Fondasi Backend dan Frontend

**Status:** implementasi selesai dan terverifikasi 2026-10-19. Gate Phase 1 belum ditandai lulus; menunggu persetujuan eksplisit pengguna sebelum Phase 2.
**Sumber:** `PLAN.md` §13 Phase 1, §14.

---

## 1. Tujuan dan Scope

Membangun kerangka aplikasi web lokal yang dapat diuji tanpa LLM nyata:

- project uv, config TOML, logging redaction, MySQL + migrasi;
- LLM gateway + fake provider, kontrak adapter provider (tanpa provider nyata);
- URL guard, CSRF, consent record, cost tracker, `gawe doctor`;
- scaffold Vite + React + TypeScript, `MantineProvider` + theme;
- komponen Mantine (`AppShell`, `Tabs`, `Table`, `Drawer`, `Modal`, `Badge`, `Alert`, `Skeleton`);
- routing, query client, API client, tipe dari OpenAPI;
- AppShell dengan navigasi utama;
- halaman placeholder ber-state.

Di luar scope: ekstraksi nyata, discovery, tailoring, LaTeX/PDF.

---

## 2. Prasyarat dan Dependensi

- Phase 0 selesai dan disetujui.
- D22 sudah final.
- D1 **tidak** dibutuhkan; fake provider cukup.
- Tidak ada keputusan UI yang tersisa; matriks versi dan kebijakan frontend ada di [`../adr/0001-frontend-stack.md`](../adr/0001-frontend-stack.md). Verifikasi instalasi, typecheck, dan build dilakukan di fase ini.
- C6 sudah diputuskan: `config.example.toml` dan `.env.example` tetap di root repository.

---

## 3. Dokumen Wajib Dibaca

1. [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md)
2. [`../source-of-truth/ARCHITECTURE.md`](../source-of-truth/ARCHITECTURE.md)
3. [`../source-of-truth/API-CONTRACTS.md`](../source-of-truth/API-CONTRACTS.md)
4. [`../source-of-truth/UI-DESIGN.md`](../source-of-truth/UI-DESIGN.md)
5. [`../source-of-truth/SECURITY.md`](../source-of-truth/SECURITY.md)
6. [`../source-of-truth/DATA-AND-PRIVACY.md`](../source-of-truth/DATA-AND-PRIVACY.md)
7. [`../domains/SYSTEM.md`](../domains/SYSTEM.md)
8. [`../domains/BACKEND.md`](../domains/BACKEND.md)
9. [`../domains/FRONTEND.md`](../domains/FRONTEND.md)
10. [`../domains/DATABASE.md`](../domains/DATABASE.md)
11. [`../domains/LLM-AND-PROMPTS.md`](../domains/LLM-AND-PROMPTS.md)
12. [`../domains/TESTING.md`](../domains/TESTING.md)

---

## 4. File atau Modul yang Diharapkan Berubah

Mengikuti proposal `PLAN.md` §12 (belum dibuat):

```text
.gitignore, config.example.toml, .env.example
backend/
  pyproject.toml, uv.lock
  src/gawe/
    __main__.py, config.py, logging.py, orchestrator.py, cli.py
    api/app.py, api/deps.py, api/routes/, api/schemas/
    services/
    db/schema.sql, db/migrations/, db/repo.py
    llm/client.py, llm/schemas.py, llm/providers/base.py,
    llm/providers/openai_compatible.py, llm/providers/local.py,
    llm/prompts/, llm/cost.py
    security/url_guard.py, security/redact.py, security/secrets.py,
    security/files.py, security/csrf.py, security/consent.py, security/sanitize.py
  tests/{unit,integration,fixtures}
frontend/
  package.json, package-lock.json, tsconfig.json, vite.config.ts, index.html
  src/main.tsx, src/app/{router.tsx,queryClient.ts,apiClient.ts,api-types.gen.ts,theme.ts}
  src/components/{AppShell,StatusBadge,EligibilityBadge,EmptyState,ErrorState,LoadingState}.tsx
  src/pages/
  src/styles/exceptions.css
  tests/
```

Perintah frontend dijalankan dari `frontend/`; perintah backend dari `backend/`. `config.example.toml` dan `.env.example` berada di root repository (C6); backend membaca config dari root.

---

## 5. Persyaratan dan Batasan

- Server hanya bind `127.0.0.1`.
- Frontend SPA React + TypeScript + Vite + Mantine.
- Mantine satu-satunya library komponen UI utama.
- Tidak ada template HTML server-side untuk halaman aplikasi.
- Tipe request/response dihasilkan dari OpenAPI.
- Fake provider; tanpa network di test.
- Config TOML; secret di keyring.
- Migrasi MySQL versioned.
- Log redaction aktif.
- CSRF untuk mutasi.
- Consent record tersedia.
- Background task in-process (kerangka).
- `gawe doctor` melaporkan environment.
- Halaman placeholder memiliki loading/empty/error/partial/retry state.

---

## 6. Keamanan, Privasi, dan Error Handling

- Bind localhost; tanpa tunnel.
- CSRF token pada mutasi; test request tanpa token.
- URL guard diuji dengan IP private/loopback/link-local.
- Redaksi log diuji dengan email/telepon/URL query.
- Debug model I/O default off.
- Tidak ada secret/PII di log test.
- Secret tidak di file konfigurasi yang di-commit.
- Error API aman; tanpa stack trace/path internal.
- Migrasi gagal → jangan serve.
- Provider gagal → error jelas (fake provider untuk test).

---

## 7. Acceptance Criteria

Dari `PLAN.md` §13 Phase 1:

- `pytest` hijau;
- fake LLM;
- tidak ada network di test;
- `doctor` melaporkan environment;
- server hanya bind localhost;
- `vite build` berhasil;
- typecheck lulus;
- tidak ada template HTML server-side untuk halaman aplikasi;
- UI memakai Mantine tanpa stylesheet aplikasi utama;
- tidak ada library komponen UI utama kedua;
- setiap pengecualian CSS terdokumentasi;
- tidak ada provider atau model nyata yang diasumsikan.

Acceptance criteria tidak diubah.

---

## 8. Cara Verifikasi dan Bukti

- `pytest` dari `backend/` + output ringkas.
- `gawe doctor`.
- Typecheck dari `frontend/`.
- `vite build` dari `frontend/`.
- Smoke test UI.
- Pemeriksaan dependency UI (tidak ada library utama kedua).
- Pemeriksaan tidak ada template HTML server-side.
- Test CSRF, URL guard, redaksi, default-off diagnostik.
- Cek bind host/port.
- Cek tidak ada network di test.

Bukti: perintah, output pass/fail, dan batasan pengujian.

---

## 9. Keputusan `OPEN` yang Dapat Memblokir

| ID | Dampak |
|---|---|
| D1 | Tidak memblokir Phase 1; fake provider cukup |
| D6 | Tidak memblokir |
| D10 | Retensi tetap sementara |
| D20 | Tidak memblokir; default tanpa auth |
| D22 | Final |

Kontrak endpoint lengkap harus sudah disetujui di Phase 0; jika belum, Phase 1 berhenti di bagian yang bergantung pada kontrak.

---

## 10. Kondisi Berhenti dan Minta Konfirmasi

Berhenti bila:

- kontrak API berubah tanpa persetujuan baru;
- muncul kebutuhan provider nyata;
- muncul kebutuhan library UI kedua atau stylesheet utama;
- muncul kebutuhan mengubah arsitektur;
- test keamanan gagal dan perbaikannya mengubah keputusan;
- ada kebocoran secret/PII di log;
- muncul kebutuhan mengubah acceptance criteria.

---

## 11. Gate Persetujuan

Phase 2 tidak boleh dimulai tanpa persetujuan eksplisit pengguna dan tanpa memenuhi gate Phase 1:

- tidak ada kebocoran secret/PII di log test;
- build frontend deterministik.

---

## 12. Referensi PLAN.md

- §4.0 A0 dan aturan UI
- §6 Arsitektur komponen
- §8 Rekomendasi stack
- §9 Data model
- §11 Security dan reliability
- §12 Struktur repo
- §13 Phase 1
- §14 kriteria 1–5, 7–11, 13–36 (yang relevan)
