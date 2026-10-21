# Fixture Phase 0 — Data Sintetis

**Status:** draft Phase 0. Semua data sintetis. Tidak ada PII nyata.

Fixture ini adalah contoh bentuk data untuk kontrak Phase 0, bukan bukti kualitas ekstraksi atau akurasi model. Jangan menambahkan data kandidat nyata.

| Path | Isi | Schema |
|---|---|---|
| `master_cv/candidate_001.md` | CV teks sintetis dengan locator | — (input teks) |
| `profiles/profile_confirmed.json` | Profil `confirmed` dengan evidence | [`../contracts/profile.schema.json`](../contracts/profile.schema.json) |
| `jobs/job_001_eligible.json` | Lowongan remote global, semua must-have terpenuhi | [`../contracts/job.schema.json`](../contracts/job.schema.json) |
| `jobs/job_002_needs_review.json` | Lowongan Indonesia remote, ketersediaan mulai tidak diketahui | [`../contracts/job.schema.json`](../contracts/job.schema.json) |
| `jobs/job_003_ineligible.json` | Lowongan Jerman onsite, wajib izin kerja EU | [`../contracts/job.schema.json`](../contracts/job.schema.json) |
| `eligibility/eligible.json` | Assessment `eligible` | [`../contracts/eligibility.schema.json`](../contracts/eligibility.schema.json) |
| `eligibility/needs_review.json` | Assessment `needs_review` | [`../contracts/eligibility.schema.json`](../contracts/eligibility.schema.json) |
| `eligibility/ineligible.json` | Assessment `ineligible` | [`../contracts/eligibility.schema.json`](../contracts/eligibility.schema.json) |
| `fit/fit_eligible.json` | Fit assessment untuk lowongan `eligible` | [`../contracts/fit-assessment.schema.json`](../contracts/fit-assessment.schema.json) |
| `findings/findings_changes_required.json` | Findings reviewer dengan `blocker` dan `major` | [`../contracts/findings.schema.json`](../contracts/findings.schema.json) |
| `ranking/ranking_cases.json` | Kasus invariant ranking | Aturan di [`../contracts/ranking.md`](../contracts/ranking.md) |
| `seeded_defects/cv_seeded_defects.md` | CV cacat buatan untuk regression reviewer | — |
| `seeded_defects/cv_seeded_defects.expected.json` | Ekspektasi temuan untuk CV cacat | — |

Aturan:

- Nama, email, telepon, perusahaan, dan URL bersifat fiktif. Domain memakai `example.com`, `example.co.id`, dan `example.de`.
- Fixture tidak memuat secret.
- Fixture tidak dipakai sebagai data runtime.
- Setelah Phase 0 disetujui, fixture dipindahkan ke `backend/tests/fixtures/` pada fase yang sesuai.

Verifikasi: `python tools/check-phase-00.py` dari root repo.
