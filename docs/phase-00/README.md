# Phase 0 — Lokasi Deliverable Draft

**Status:** deliverable Phase 0 lengkap dan disetujui pengguna 2026-10-19. Gate Phase 0 lulus. Phase 1 belum dimulai.
**Acuan:** [`../phases/PHASE-00.md`](../phases/PHASE-00.md) §4; [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) C6.

Phase 0 tidak membuat kode aplikasi atau scaffold. Semua deliverable draft Phase 0 yang berupa teks berada di bawah `docs/`.

---

## 1. Path Draft Phase 0

| Deliverable | Path draft | Status |
|---|---|---|
| Prompt draft | `docs/phase-00/prompts/` (6 file) | Ada, draft |
| Fixture contoh | `docs/phase-00/fixtures/` | Ada, sintetis |
| JSON schema Master CV/profil/job/eligibility/assessment/findings | `docs/phase-00/contracts/*.schema.json` (6 file) | Disetujui 2026-10-19 |
| Kontrak OpenAPI awal | `docs/phase-00/contracts/openapi.yaml` | Disetujui 2026-10-19 (C4 ditutup) |
| Kontrak `LLMClient` | `docs/phase-00/contracts/llm-client.md` | Ada, draft |
| Aturan ranking | `docs/phase-00/contracts/ranking.md` + fixture invariant | Ada, draft |
| Config provider contoh | `config.example.toml`, `.env.example` di root | Ada; C6 selesai 2026-10-19 (root) |

Daftar lengkap:

```text
docs/phase-00/
  README.md
  contracts/
    openapi.yaml
    master-cv.schema.json
    profile.schema.json
    job.schema.json
    eligibility.schema.json
    fit-assessment.schema.json
    findings.schema.json
    llm-client.md
    ranking.md
  prompts/
    extract_profile.md
    parse_requirements.md
    classify_priority.md
    write_cv.md
    write_cover_letter.md
    review.md
  fixtures/
    README.md
    master_cv/candidate_001.md
    profiles/profile_confirmed.json
    jobs/job_001_eligible.json
    jobs/job_002_needs_review.json
    jobs/job_003_ineligible.json
    eligibility/eligible.json
    eligibility/needs_review.json
    eligibility/ineligible.json
    fit/fit_eligible.json
    findings/findings_changes_required.json
    ranking/ranking_cases.json
    seeded_defects/cv_seeded_defects.md
    seeded_defects/cv_seeded_defects.expected.json
```

Semua isi di atas adalah deliverable Phase 0, bukan artefak runtime. Schema dan kontrak OpenAPI sudah disetujui dan menjadi acuan final; prompt, fixture, dan catatan kontrak lain tetap draft sampai dipakai di fase implementasinya.

Verifikasi: `python tools/check-phase-00.py` dari root repo.

---

## 2. Path Implementasi Target (bukan dibuat di Phase 0)

| Draft Phase 0 | Target implementasi |
|---|---|
| `docs/phase-00/prompts/` | `backend/src/gawe/llm/prompts/` |
| `docs/phase-00/fixtures/` | `backend/tests/fixtures/` |
| `docs/phase-00/contracts/*.schema.json` | schema Pydantic + tabel MySQL pada Phase 1 |
| `docs/phase-00/contracts/openapi.*` | OpenAPI yang dihasilkan backend pada Phase 1 |
| `docs/phase-00/contracts/llm-client.md` | `backend/src/gawe/llm/client.py` pada Phase 1 |
| `docs/phase-00/contracts/ranking.md` | `backend/src/gawe/ranking/` pada Phase 3–4 |

Path target hanya referensi. Jangan membuat direktori `backend/` atau `frontend/` selama Phase 0.

---

## 3. Config Contoh

- Draft `config.example.toml` dan `.env.example` boleh disimpan di root pada Phase 0.
- Keduanya hanya memuat placeholder. Tidak ada provider, model, atau secret nyata.
- `config.example.toml` dan `.env.example` berada di root repository sebagai template konfigurasi (C6, selesai 2026-10-19). Lihat [`../source-of-truth/DECISIONS.md`](../source-of-truth/DECISIONS.md) C6.

---

## 4. Aturan

- Schema dan kontrak API di `docs/phase-00/` disetujui 2026-10-19 dan menjadi acuan final; perubahan memerlukan persetujuan baru.
- Draft tidak memuat data kandidat nyata, secret, atau PII.
- Prompt draft netral provider: tanpa nama vendor atau model.
- Fixture draft memakai data sintetis.
- Setelah Phase 0 disetujui, draft dipindahkan ke path implementasi pada fase yang sesuai, bukan disalin ganda.
