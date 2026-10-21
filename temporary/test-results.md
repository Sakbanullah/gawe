# Backend test results

## Run 2026-10-21 10:02 +07:00 - optimasi fixture test (isolasi DB per module)

Command: `.\.venv\Scripts\python.exe -m pytest -o addopts="" --tb=short -p no:warnings -q`

Working directory: `D:\gawe\backend`

### Baseline sebelum optimasi (diukur pada working tree yang sama)

- Perintah: `.\.venv\Scripts\python.exe -m pytest -o addopts="" --tb=short -p no:warnings -q`
- Waktu: 2026-10-21 09:52 +07:00
- Hasil: **317 passed, 1 skipped in 230.07s**, exit code 0, wall 232.01s.
- Baseline ini konsisten dengan run 09:44 di bawah (229.95s, 317 passed). Selisih 0.12s.

### Penyebab yang terbukti

Bottleneck bukan satu test, bukan network, bukan plugin. Fixture `_clean_database` di `backend/tests/conftest.py` memakai `autouse=True`, sehingga setiap test (termasuk test murni tanpa DB) menjalankan `repo.reset()`.

Pengukuran langsung pada schema scratch 22 tabel (`temporary/audit/probe_reset_cost.py`, dijalankan 2026-10-21 09:57, 15 iterasi):

| Operasi | median | mean | min | max |
|---|---:|---:|---:|---:|
| `reset()` lama (22 TRUNCATE) | 742.5 ms | 746.8 ms | 681.9 ms | 794.6 ms |
| `reset()` baru (DELETE dalam 1 transaksi) | 6.9 ms | 8.3 ms | 5.4 ms | 30.2 ms |
| connect + list tabel | 15.1 ms | - | - | - |

MySQL 8.0.30 pada mesin ini: `innodb_flush_log_at_trx_commit=1`, `sync_binlog=1`. TRUNCATE adalah DDL autocommit, jadi tiap tabel memaksa commit + flush sendiri. Tidak ada kolom `AUTO_INCREMENT` di seluruh migrasi (`Select-String` pada `src/gawe/db/migrations/*.sql` = 0 match), jadi counter yang biasanya di-reset TRUNCATE tidak ada.

### Perubahan yang diterapkan

1. `backend/tests/conftest.py`: `_clean_database` tidak lagi `autouse=True`. Fixture `connection` dan `setup_client` memintanya secara eksplisit, sehingga semua test yang memakai keduanya tetap terisolasi.
2. `backend/tests/conftest.py`: docstring `_clean_database` menjelaskan cara opt-in untuk module yang menyentuh DB lewat `config`/`repo_root`.
3. `backend/tests/test_api.py`, `backend/tests/test_settings_consent.py`: tambah `pytestmark = pytest.mark.usefixtures("_clean_database")`. Kedua module membangun app lewat fixture `config` (bukan `setup_client`) dan mengandalkan state kosong.
4. `backend/tests/test_live_9router.py`: `test_live_9router_extraction` meminta `_clean_database` secara eksplisit. Test tetap opt-in dan tetap skipped secara default.
5. `backend/src/gawe/db/repo.py` `reset()`: 22 `TRUNCATE TABLE` diganti `DELETE FROM` untuk semua tabel di dalam satu transaksi. Nama tabel, pengecualian `schema_version`, dan `SET FOREIGN_KEY_CHECKS` tidak berubah.

Tidak ada test dihapus, tidak ada assertion dikurangi, tidak ada timeout keamanan diubah, tidak ada durability MySQL diubah, subprocess parser tidak disentuh.

### Validasi bertahap (semua exit code 0)

| Cakupan | Perintah | Hasil | Wall |
|---|---|---|---|
| Test murni tanpa DB (6 module) | `pytest ... tests/test_csrf.py tests/test_redact.py tests/test_url_guard.py tests/test_project_rules.py tests/test_discovery_adapters.py tests/test_config.py` | 72 passed in 0.42s | 2.23s |
| DB inti (7 module) | `pytest ... tests/test_db.py tests/test_llm.py tests/test_consent.py tests/test_provider_integration.py tests/test_api.py tests/test_settings_consent.py tests/test_doctor.py` | 68 passed in 6.48s | 8.22s |
| Integrasi API (9 module) | `pytest ... tests/test_applications.py tests/test_assessment.py tests/test_documents.py tests/test_discovery.py tests/test_discovery_dedupe.py tests/test_ingest.py tests/test_profile.py tests/test_sources.py tests/test_live_9router.py` | 177 passed, 1 skipped in 43.06s | 45.12s |

Bukti test tanpa DB tidak lagi melakukan reset: 72 test murni selesai 0.42s. Sebelumnya test yang sama menanggung ~0.7s/test hanya untuk reset (lihat `test_redact.py` 0.725-0.827s di run 3D).

### Full suite setelah optimasi

| Run | Waktu | Hasil | Wall |
|---|---|---|---|
| 1 | 2026-10-21 09:59 | **317 passed, 1 skipped in 48.38s** | 50.24s |
| 2 | 2026-10-21 10:01 | **317 passed, 1 skipped in 48.35s** | 50.31s |

Run kedua dijalankan untuk memeriksa stabilitas/order dependency. Hasil identik, selisih 0.03s.

### Perbandingan

- Baseline: 230.07s
- Setelah: 48.38s
- Pengurangan: **181.69s (79.0%)**
- Target awal maksimal 120s untuk ~315 test: **terpenuhi**, aktual 48.38s untuk 317 test.
- Jumlah test tidak berubah: 317 passed + 1 skipped, sama dengan baseline. Tidak ada test yang di-skip baru.

### Batasan

- Durasi diukur pada mesin yang sama, MySQL lokal yang sama, tanpa network live, dengan fake provider.
- Test yang skipped tetap `tests/test_live_9router.py::test_live_9router_extraction` (opt-in, butuh `GAWE_LIVE_9ROUTER=1`).
- Optimasi koneksi per-session tidak dikerjakan: tidak terbukti diperlukan setelah target tercapai.
- Optimasi `migrate()` (query `applied_versions` berulang) tidak dikerjakan: dampaknya di bawah 2s dan tidak diperlukan untuk target.
- `DELETE FROM` tidak me-reset AUTO_INCREMENT. Aman sekarang karena tidak ada kolom AUTO_INCREMENT; dicatat sebagai komentar di `reset()` agar ditinjau ulang bila kolom itu ditambahkan.

### Lingkungan database

Tujuh schema `gawe_test_*` sisa run sebelumnya teridentifikasi dan **tidak dihapus**: `gawe_test_9732875980fc` (16 tabel), `gawe_test_26fc56659db2` (16), `gawe_test_4b973af8d875` (19), `gawe_test_c38f1587782a` (19), `gawe_test_c04a3a36c6d2` (20), `gawe_test_c1e03d1f62ab` (22), `gawe_test_4f1f05b3cf4d` (23). Tidak mengganggu validasi: tiap run membuat schema sendiri via `uuid4`, dan durasi turun konsisten.

Schema scratch `gawe_test_audit_reset_8a678600` yang dibuat probe pengukuran sudah di-drop oleh probe itu sendiri.

---

## Run 2026-10-21 09:44 +07:00 - milestone 3D dokumen/versi/review/approval (final)

Command: `.\.venv\Scripts\python.exe -m pytest -o addopts="" --tb=no -p no:warnings`

Working directory: `D:\gawe\backend`

Note: `-o addopts=""` clears the `-q` from `pyproject.toml` so pytest prints the summary. No other option changes test behavior.

### Summary

- PASSED: 317
- FAILED: 0
- ERROR: 0
- SKIPPED: 1 (`tests/test_live_9router.py`, opt-in live provider)
- Duration: 229.95s (3m 49.95s)
- Exit code: 0

### Scope

- Baru: `tests/test_documents.py` (20 test) - draft deterministik, hash canonical, diff Master CV/versi induk, gate eligibility (`needs_review`, `ineligible`, `status_outdated`), review deterministik (evidence wajib, evidence tidak dikenal), findings, approval terikat versi + hash, replay, deteksi konten berubah di luar alur, versi approved menolak keputusan/review lain, revisi tidak mewarisi approval, data wajib, eligibility dicek ulang, cover letter dengan klaim bisa disetujui, regenerate, CSRF, pagination, path/tipe edit invalid, dan field terlindungi (`kind`, `schema_version`, `target`, `language`, `evidence_ids`).
- Diperbarui: `tests/test_applications.py` (next action `review_documents`), `tests/test_db.py` (migrasi `0011_documents` + tabel baru), `tests/test_api.py`, `tests/test_doctor.py` (versi skema).
- Seluruh suite backend dijalankan karena perubahan menyentuh migrasi, service bersama, dan fixture.

Frontend (dijalankan terpisah pada 2026-10-21 09:39 +07:00):

- `npm run test` -> `Test Files 7 passed (7)`, `Tests 39 passed (39)`, 50.71s.
- `npm run typecheck` -> tanpa error (dijalankan 2026-10-21 01:47 +07:00).
- Build tidak dijalankan pada increment ini.

Batasan: tanpa network live, tanpa data kandidat nyata, tanpa uji UI manual. PDF/ekspor/reviewer LLM tidak diuji karena belum diimplementasikan.

### Verifikasi setelah perubahan terakhir

Setelah run suite di atas, satu baris `regenerate` diubah agar memakai `job_posting_version_id` dari eligibility workspace (bukan nilai induk). Perubahan hanya menyentuh `document_service.regenerate` dan dicakup `tests/test_documents.py`.

- Perintah: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_documents.py -o addopts="" --tb=short -p no:warnings -q`
- Waktu: 2026-10-21 09:47 +07:00
- Hasil: `20 passed in 21.20s`, exit code 0.
- Suite penuh tidak diulang setelah perubahan satu baris ini; hasil suite penuh di atas adalah hasil sebelum perubahan tersebut. Frontend tidak berubah setelah `npm run test` 09:39.

---

## Run sebelumnya (2026-10-20) - sebelum milestone 3D

Command: `.\\.venv\\Scripts\\python.exe -m pytest -v -p no:warnings`

Working directory: `D:\gawe\backend`

Note: run used `-o addopts=` so the `-q` in `backend/pyproject.toml` does not cancel verbose output. No other option changes test behavior.

## Summary

- Collected: 298
- PASSED: 297
- FAILED: 0
- SKIPPED: 1
- ERROR: 0
- Total duration: 269.71s (4m 29.71s)
- Exit code: 0

## Per-test results

| # | Test | Status | Duration (s) |
|---:|---|---|---:|
| 1 | `tests/test_api.py::test_session_sets_cookies_and_returns_token` | PASSED | 2.347 |
| 2 | `tests/test_api.py::test_overview_shape` | PASSED | 0.818 |
| 3 | `tests/test_api.py::test_mutation_without_csrf_is_rejected` | PASSED | 0.865 |
| 4 | `tests/test_api.py::test_mutation_with_valid_csrf_reaches_routing` | PASSED | 1.233 |
| 5 | `tests/test_api.py::test_app_does_not_hold_a_shared_connection` | PASSED | 1.672 |
| 6 | `tests/test_api.py::test_startup_runs_migrations` | PASSED | 1.388 |
| 7 | `tests/test_applications.py::test_filename_follows_contract_format_and_sanitises` | PASSED | 0.959 |
| 8 | `tests/test_applications.py::test_filename_falls_back_and_strips_illegal_characters` | PASSED | 0.869 |
| 9 | `tests/test_applications.py::test_filename_collision_suffix_is_stable_and_bounded` | PASSED | 0.863 |
| 10 | `tests/test_applications.py::test_application_requires_confirmed_profile` | PASSED | 0.972 |
| 11 | `tests/test_applications.py::test_create_application_from_job_is_idempotent` | PASSED | 1.623 |
| 12 | `tests/test_applications.py::test_workspace_shows_job_eligibility_and_suggested_filenames` | PASSED | 2.144 |
| 13 | `tests/test_applications.py::test_workspace_keeps_needs_review_blocked` | PASSED | 1.734 |
| 14 | `tests/test_applications.py::test_application_job_and_eligibility_endpoints` | PASSED | 1.583 |
| 15 | `tests/test_applications.py::test_manual_url_fallback_is_not_implemented_yet` | PASSED | 1.119 |
| 16 | `tests/test_applications.py::test_rerun_analysis_is_explicit_and_leaves_scores_stable` | PASSED | 1.291 |
| 17 | `tests/test_applications.py::test_second_analysis_is_rejected_with_the_active_task_id` | PASSED | 1.230 |
| 18 | `tests/test_applications.py::test_list_applications_filters_by_status_and_rejects_bad_cursor` | PASSED | 1.328 |
| 19 | `tests/test_applications.py::test_rerun_analysis_requires_csrf` | PASSED | 1.224 |
| 20 | `tests/test_assessment.py::test_priority_tier_classification[Berlin, Germany-onsite--P1]` | PASSED | 0.752 |
| 21 | `tests/test_assessment.py::test_priority_tier_classification[Berlin, Germany-hybrid--P1]` | PASSED | 0.790 |
| 22 | `tests/test_assessment.py::test_priority_tier_classification[Remote - Worldwide-remote--P2]` | PASSED | 0.684 |
| 23 | `tests/test_assessment.py::test_priority_tier_classification[Remote-remote-open to candidates anywhere-P2]` | PASSED | 0.707 |
| 24 | `tests/test_assessment.py::test_priority_tier_classification[Jakarta, Indonesia-remote--P3]` | PASSED | 0.694 |
| 25 | `tests/test_assessment.py::test_priority_tier_classification[Jakarta, Indonesia-hybrid--P4]` | PASSED | 0.759 |
| 26 | `tests/test_assessment.py::test_priority_tier_classification[Jakarta, Indonesia-onsite--P4]` | PASSED | 0.750 |
| 27 | `tests/test_assessment.py::test_priority_tier_classification[Remote-remote--unclassified]` | PASSED | 0.689 |
| 28 | `tests/test_assessment.py::test_priority_tier_classification[Berlin-onsite--unclassified]` | PASSED | 0.749 |
| 29 | `tests/test_assessment.py::test_priority_tier_classification[-remote--unclassified]` | PASSED | 0.796 |
| 30 | `tests/test_assessment.py::test_priority_tier_classification[Jakarta, Indonesia-unknown--unclassified]` | PASSED | 0.849 |
| 31 | `tests/test_assessment.py::test_priority_classification_carries_reason_and_confidence` | PASSED | 0.740 |
| 32 | `tests/test_assessment.py::test_requirement_extraction_marks_must_and_nice_with_quotes` | PASSED | 0.688 |
| 33 | `tests/test_assessment.py::test_requirement_extraction_is_stable_and_skips_responsibilities` | PASSED | 0.752 |
| 34 | `tests/test_assessment.py::test_eligible_job_with_met_experience` | PASSED | 0.667 |
| 35 | `tests/test_assessment.py::test_missing_work_authorization_is_ineligible_with_quote` | PASSED | 0.719 |
| 36 | `tests/test_assessment.py::test_unknown_requirement_is_needs_review_not_eligible` | PASSED | 0.733 |
| 37 | `tests/test_assessment.py::test_job_without_must_have_requirements_is_needs_review` | PASSED | 0.721 |
| 38 | `tests/test_assessment.py::test_profile_without_confirmed_authorization_needs_review` | PASSED | 0.727 |
| 39 | `tests/test_assessment.py::test_fit_formula_and_verdict` | PASSED | 0.714 |
| 40 | `tests/test_assessment.py::test_fit_is_weak_when_must_coverage_below_half` | PASSED | 0.716 |
| 41 | `tests/test_assessment.py::test_ranking_fixture_cases[identical_scores_tier_then_posted_at]` | PASSED | 0.732 |
| 42 | `tests/test_assessment.py::test_ranking_fixture_cases[tie_window_five_band]` | PASSED | 0.797 |
| 43 | `tests/test_assessment.py::test_ranking_fixture_cases[tier_never_crosses_band]` | PASSED | 0.741 |
| 44 | `tests/test_assessment.py::test_ranking_fixture_cases[unclassified_last_in_band]` | PASSED | 0.754 |
| 45 | `tests/test_assessment.py::test_ranking_fixture_cases[non_eligible_excluded]` | PASSED | 0.693 |
| 46 | `tests/test_assessment.py::test_ranking_fixture_cases[null_posted_at_last_in_band]` | PASSED | 0.749 |
| 47 | `tests/test_assessment.py::test_ranking_fixture_cases[deterministic_under_shuffle]` | PASSED | 0.730 |
| 48 | `tests/test_assessment.py::test_ranking_rejects_fit_score_on_needs_review` | PASSED | 0.732 |
| 49 | `tests/test_assessment.py::test_ranking_rejects_out_of_range_tie_window` | PASSED | 0.638 |
| 50 | `tests/test_assessment.py::test_tier_change_does_not_change_fit_score` | PASSED | 0.673 |
| 51 | `tests/test_assessment.py::test_discovery_run_assesses_jobs_and_exposes_matches` | PASSED | 1.162 |
| 52 | `tests/test_assessment.py::test_matches_filters_do_not_change_stored_scores` | PASSED | 1.099 |
| 53 | `tests/test_assessment.py::test_match_detail_separates_eligibility_and_fit` | PASSED | 1.167 |
| 54 | `tests/test_assessment.py::test_match_detail_unknown_job_is_404` | PASSED | 1.092 |
| 55 | `tests/test_assessment.py::test_matches_requires_confirmed_profile` | PASSED | 0.875 |
| 56 | `tests/test_assessment.py::test_overview_counts_come_from_assessments` | PASSED | 1.168 |
| 57 | `tests/test_assessment.py::test_reassessment_is_idempotent` | PASSED | 1.295 |
| 58 | `tests/test_assessment.py::test_matches_cursor_pages_without_offset` | PASSED | 1.195 |
| 59 | `tests/test_assessment.py::test_matches_rejects_invalid_or_foreign_cursor` | PASSED | 1.131 |
| 60 | `tests/test_assessment.py::test_description_truncation_respects_contract_limits` | PASSED | 0.684 |
| 61 | `tests/test_assessment.py::test_match_detail_matches_job_detail_contract` | PASSED | 1.143 |
| 62 | `tests/test_assessment.py::test_tier_override_is_stored_and_leaves_fit_alone` | PASSED | 1.142 |
| 63 | `tests/test_assessment.py::test_tier_override_validation` | PASSED | 1.058 |
| 64 | `tests/test_assessment.py::test_assessment_failure_is_visible_on_run` | PASSED | 1.067 |
| 65 | `tests/test_config.py::test_loads_config` | PASSED | 0.545 |
| 66 | `tests/test_config.py::test_rejects_invalid_database_name` | PASSED | 0.497 |
| 67 | `tests/test_config.py::test_rejects_reserved_database_name` | PASSED | 0.869 |
| 68 | `tests/test_config.py::test_password_comes_from_environment` | PASSED | 0.924 |
| 69 | `tests/test_config.py::test_rejects_non_loopback_host` | PASSED | 0.841 |
| 70 | `tests/test_config.py::test_rejects_missing_file` | PASSED | 0.648 |
| 71 | `tests/test_config.py::test_rejects_model_io_logging` | PASSED | 0.725 |
| 72 | `tests/test_config.py::test_key_source_never_returns_value` | PASSED | 0.769 |
| 73 | `tests/test_config.py::test_resolve_api_key_prefers_keyring_over_env` | PASSED | 0.706 |
| 74 | `tests/test_config.py::test_resolve_api_key_falls_back_to_env` | PASSED | 0.811 |
| 75 | `tests/test_config.py::test_resolve_api_key_reads_env_without_a_ref` | PASSED | 0.756 |
| 76 | `tests/test_config.py::test_resolve_api_key_returns_none_when_unavailable` | PASSED | 0.694 |
| 77 | `tests/test_config.py::test_resolve_api_key_survives_keyring_error` | PASSED | 0.735 |
| 78 | `tests/test_config.py::test_resolve_api_key_uses_the_requested_env_var` | PASSED | 0.768 |
| 79 | `tests/test_config.py::test_resolved_api_key_never_reaches_config_output` | PASSED | 0.749 |
| 80 | `tests/test_consent.py::test_consent_required_before_grant` | PASSED | 0.713 |
| 81 | `tests/test_consent.py::test_grant_persists_text_version_and_scope` | PASSED | 0.809 |
| 82 | `tests/test_consent.py::test_status_reports_granted_and_history` | PASSED | 0.737 |
| 83 | `tests/test_consent.py::test_revoke_marks_record_and_blocks_provider` | PASSED | 0.773 |
| 84 | `tests/test_consent.py::test_revoke_unknown_or_twice_fails` | PASSED | 0.711 |
| 85 | `tests/test_consent.py::test_expired_text_version_requires_new_consent` | PASSED | 0.764 |
| 86 | `tests/test_consent.py::test_provider_or_model_change_invalidates_consent` | PASSED | 0.801 |
| 87 | `tests/test_consent.py::test_fake_provider_needs_no_consent` | PASSED | 0.813 |
| 88 | `tests/test_csrf.py::test_safe_method_needs_no_token` | PASSED | 0.794 |
| 89 | `tests/test_csrf.py::test_missing_token_is_rejected` | PASSED | 0.820 |
| 90 | `tests/test_csrf.py::test_wrong_token_is_rejected` | PASSED | 0.552 |
| 91 | `tests/test_csrf.py::test_valid_token_is_accepted` | PASSED | 0.510 |
| 92 | `tests/test_csrf.py::test_foreign_origin_is_rejected` | PASSED | 0.552 |
| 93 | `tests/test_csrf.py::test_cross_site_fetch_is_rejected` | PASSED | 0.557 |
| 94 | `tests/test_csrf.py::test_dev_proxy_origin_is_accepted` | PASSED | 0.950 |
| 95 | `tests/test_db.py::test_migration_applies_and_is_idempotent` | PASSED | 1.029 |
| 96 | `tests/test_db.py::test_tables_exist` | PASSED | 0.832 |
| 97 | `tests/test_db.py::test_consent_migration_handles_unapplied_and_partial_schema` | PASSED | 2.479 |
| 98 | `tests/test_db.py::test_failed_migration_records_nothing` | PASSED | 0.796 |
| 99 | `tests/test_db.py::test_duplicate_master_cv_sha256_is_rejected` | PASSED | 0.750 |
| 100 | `tests/test_db.py::test_profile_version_number_is_unique_per_profile` | PASSED | 0.716 |
| 101 | `tests/test_db.py::test_only_one_active_profile_version` | PASSED | 0.713 |
| 102 | `tests/test_db.py::test_inactive_profile_versions_are_unlimited` | PASSED | 0.595 |
| 103 | `tests/test_db.py::test_foreign_key_rejects_unknown_master_cv` | PASSED | 0.703 |
| 104 | `tests/test_db.py::test_discovery_foreign_keys_reject_orphans[INSERT INTO discovery_run (run_id, task_id, profile_version_id, status, counts_json, started_at) VALUES ('run_x', 'missing', 'missing', 'queued', '{}', '2026-10-20T00:00:00Z')]` | PASSED | 0.595 |
| 105 | `tests/test_db.py::test_discovery_foreign_keys_reject_orphans[INSERT INTO source_fetch (fetch_id, run_id, source_id, status, fetched_at, raw_sha256, raw_json) VALUES ('fet_x', 'run_x', 'missing', 'completed', '2026-10-20T00:00:00Z', 'x', '{}')]` | PASSED | 0.691 |
| 106 | `tests/test_db.py::test_discovery_foreign_keys_reject_orphans[INSERT INTO job (job_id, source_id, source_job_id, canonical_url, company, title, location_json, work_mode, employment_type, seniority, market, fetched_at, status, completeness_json, created_at, updated_at) VALUES ('job_x', 'missing', '1', 'https://example.com/1', 'Acme', 'Engineer', '{}', 'onsite', 'full_time', 'unknown', 'unknown', '2026-10-20T00:00:00Z', 'open', '{}', '2026-10-20T00:00:00Z', '2026-10-20T00:00:00Z')]` | PASSED | 0.859 |
| 107 | `tests/test_db.py::test_multi_table_transaction_rolls_back` | PASSED | 0.833 |
| 108 | `tests/test_db.py::test_confirm_rolls_back_when_decision_write_fails` | PASSED | 0.797 |
| 109 | `tests/test_db.py::test_drop_schema_rejects_non_test_names` | PASSED | 0.768 |
| 110 | `tests/test_db.py::test_require_test_schema_rejects_development_schema` | PASSED | 0.785 |
| 111 | `tests/test_db.py::test_drop_schema_never_targets_development_schema` | PASSED | 0.842 |
| 112 | `tests/test_db.py::test_reset_keeps_schema_and_migration_history` | PASSED | 1.496 |
| 113 | `tests/test_db.py::test_ensure_schema_is_idempotent` | PASSED | 0.766 |
| 114 | `tests/test_discovery.py::test_no_discovery_without_confirmed_profile` | PASSED | 0.840 |
| 115 | `tests/test_discovery.py::test_run_stores_jobs_with_source_and_raw_hash` | PASSED | 1.429 |
| 116 | `tests/test_discovery.py::test_one_failed_source_keeps_partial_results` | PASSED | 1.255 |
| 117 | `tests/test_discovery.py::test_unverified_source_is_skipped_not_fetched` | PASSED | 1.076 |
| 118 | `tests/test_discovery.py::test_no_enabled_sources_is_a_gate` | PASSED | 1.061 |
| 119 | `tests/test_discovery.py::test_parallel_fetch_is_capped_at_three` | PASSED | 1.615 |
| 120 | `tests/test_discovery.py::test_fetch_all_stops_at_the_run_deadline` | PASSED | 1.828 |
| 121 | `tests/test_discovery.py::test_rate_limiter_reserves_one_slot_per_host_per_second` | PASSED | 0.727 |
| 122 | `tests/test_discovery.py::test_app_shares_one_limiter_across_requests` | PASSED | 0.752 |
| 123 | `tests/test_discovery.py::test_http_fetch_stops_on_403_and_429` | PASSED | 0.719 |
| 124 | `tests/test_discovery.py::test_http_fetch_rejects_host_outside_allowlist` | PASSED | 0.743 |
| 125 | `tests/test_discovery.py::test_http_fetch_accepts_only_json_content_types[application/json-True]` | PASSED | 0.745 |
| 126 | `tests/test_discovery.py::test_http_fetch_accepts_only_json_content_types[application/json; charset=utf-8-True]` | PASSED | 0.654 |
| 127 | `tests/test_discovery.py::test_http_fetch_accepts_only_json_content_types[application/vnd.api+json-True]` | PASSED | 0.603 |
| 128 | `tests/test_discovery.py::test_http_fetch_accepts_only_json_content_types[text/html; charset=utf-8-False]` | PASSED | 0.602 |
| 129 | `tests/test_discovery.py::test_http_fetch_accepts_only_json_content_types[text/plain-False]` | PASSED | 0.676 |
| 130 | `tests/test_discovery.py::test_access_denied_source_does_not_stop_others[403]` | PASSED | 1.108 |
| 131 | `tests/test_discovery.py::test_access_denied_source_does_not_stop_others[429]` | PASSED | 1.594 |
| 132 | `tests/test_discovery.py::test_retry_defaults_to_failed_sources_keeping_successful_results` | PASSED | 1.438 |
| 133 | `tests/test_discovery.py::test_retry_scope_all_repeats_every_source` | PASSED | 1.331 |
| 134 | `tests/test_discovery.py::test_retry_scope_failed_sources_rejected_for_other_tasks` | PASSED | 0.946 |
| 135 | `tests/test_discovery.py::test_duplicate_source_ids_are_deduplicated` | PASSED | 1.146 |
| 136 | `tests/test_discovery.py::test_persist_failure_fails_source_not_whole_run` | PASSED | 1.041 |
| 137 | `tests/test_discovery.py::test_run_insert_failure_rolls_back_task` | PASSED | 1.216 |
| 138 | `tests/test_discovery.py::test_concurrent_start_is_rejected_and_lock_is_released` | PASSED | 1.132 |
| 139 | `tests/test_discovery.py::test_repeated_content_reuses_version_and_keeps_latest_pointer` | PASSED | 1.315 |
| 140 | `tests/test_discovery.py::test_updated_content_refreshes_job_summary_columns` | PASSED | 1.218 |
| 141 | `tests/test_discovery.py::test_overview_reflects_latest_discovery_run` | PASSED | 1.168 |
| 142 | `tests/test_discovery.py::test_run_history_paginates_by_started_at_and_run_id` | PASSED | 1.407 |
| 143 | `tests/test_discovery.py::test_truncated_description_is_persisted` | PASSED | 1.179 |
| 144 | `tests/test_discovery.py::test_run_reports_records_the_adapter_dropped` | PASSED | 1.044 |
| 145 | `tests/test_discovery.py::test_empty_snapshot_does_not_close_jobs` | PASSED | 1.181 |
| 146 | `tests/test_discovery.py::test_invalid_snapshot_does_not_close_jobs` | PASSED | 1.337 |
| 147 | `tests/test_discovery.py::test_high_invalid_ratio_does_not_close_jobs` | PASSED | 1.236 |
| 148 | `tests/test_discovery.py::test_truncated_payload_does_not_close_jobs` | PASSED | 1.195 |
| 149 | `tests/test_discovery.py::test_jobs_absent_from_successful_fetch_are_closed_not_deleted` | PASSED | 1.354 |
| 150 | `tests/test_discovery.py::test_restricted_and_disabled_sources_are_skipped` | PASSED | 1.222 |
| 151 | `tests/test_discovery.py::test_unexpected_fetch_exception_fails_run_without_blocking_next_run` | PASSED | 1.221 |
| 152 | `tests/test_discovery.py::test_stale_discovery_task_is_recovered` | PASSED | 1.240 |
| 153 | `tests/test_discovery.py::test_adapter_error_from_build_url_is_contained` | PASSED | 1.094 |
| 154 | `tests/test_discovery_adapters.py::test_adapter_parses_fixture_and_matches_job_schema[greenhouse-greenhouse_board.json-2]` | PASSED | 0.849 |
| 155 | `tests/test_discovery_adapters.py::test_adapter_parses_fixture_and_matches_job_schema[lever-lever_postings.json-2]` | PASSED | 0.741 |
| 156 | `tests/test_discovery_adapters.py::test_adapter_parses_fixture_and_matches_job_schema[ashby-ashby_job_board.json-1]` | PASSED | 0.777 |
| 157 | `tests/test_discovery_adapters.py::test_adapter_builds_documented_endpoints` | PASSED | 0.787 |
| 158 | `tests/test_discovery_adapters.py::test_greenhouse_content_is_unescaped_twice` | PASSED | 0.816 |
| 159 | `tests/test_discovery_adapters.py::test_ashby_skips_unlisted_records` | PASSED | 0.710 |
| 160 | `tests/test_discovery_adapters.py::test_adapters_report_how_many_records_they_dropped[greenhouse-{"jobs": ["not a record", {"title": "no id"}]}-2]` | PASSED | 0.805 |
| 161 | `tests/test_discovery_adapters.py::test_adapters_report_how_many_records_they_dropped[lever-[null, {"text": "no id"}]-2]` | PASSED | 0.717 |
| 162 | `tests/test_discovery_adapters.py::test_adapters_report_how_many_records_they_dropped[ashby-{"jobs": [{"id": "a", "isListed": false}, 7]}-2]` | PASSED | 0.728 |
| 163 | `tests/test_discovery_adapters.py::test_hybrid_is_marked_and_remote_detected` | PASSED | 0.743 |
| 164 | `tests/test_discovery_adapters.py::test_empty_board_is_not_an_error` | PASSED | 0.769 |
| 165 | `tests/test_discovery_adapters.py::test_normalize_rejects_empty_source_job_id` | PASSED | 0.598 |
| 166 | `tests/test_discovery_adapters.py::test_parse_timestamp_normalises_known_shapes_and_drops_unknown[None-None]` | PASSED | 0.580 |
| 167 | `tests/test_discovery_adapters.py::test_parse_timestamp_normalises_known_shapes_and_drops_unknown[-None]` | PASSED | 0.594 |
| 168 | `tests/test_discovery_adapters.py::test_parse_timestamp_normalises_known_shapes_and_drops_unknown[not a date-None]` | PASSED | 0.613 |
| 169 | `tests/test_discovery_adapters.py::test_parse_timestamp_normalises_known_shapes_and_drops_unknown[2026-10-20-2026-10-20T00:00:00Z]` | PASSED | 0.722 |
| 170 | `tests/test_discovery_adapters.py::test_parse_timestamp_normalises_known_shapes_and_drops_unknown[2026-10-20T07:30:00Z-2026-10-20T07:30:00Z]` | PASSED | 0.986 |
| 171 | `tests/test_discovery_adapters.py::test_parse_timestamp_normalises_known_shapes_and_drops_unknown[2026-10-20T07:30:00+07:00-2026-10-20T00:30:00Z]` | PASSED | 0.745 |
| 172 | `tests/test_discovery_adapters.py::test_parse_timestamp_normalises_known_shapes_and_drops_unknown[1760941800000-2025-10-20T06:30:00Z]` | PASSED | 0.768 |
| 173 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Senior Backend Engineer-senior]` | PASSED | 0.750 |
| 174 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Sr. Data Engineer-senior]` | PASSED | 0.789 |
| 175 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Principal Engineer-principal]` | PASSED | 0.867 |
| 176 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Staff Engineer-unknown]` | PASSED | 0.821 |
| 177 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Engineering Lead-lead]` | PASSED | 0.770 |
| 178 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Junior Developer-junior]` | PASSED | 0.635 |
| 179 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Software Engineering Intern-intern]` | PASSED | 0.632 |
| 180 | `tests/test_discovery_adapters.py::test_seniority_is_derived_only_from_clear_title_signals[Backend Engineer-unknown]` | PASSED | 0.618 |
| 181 | `tests/test_discovery_adapters.py::test_market_requires_an_explicit_country_name` | PASSED | 0.607 |
| 182 | `tests/test_discovery_adapters.py::test_normalize_applies_seniority_and_market_from_payload` | PASSED | 0.691 |
| 183 | `tests/test_discovery_dedupe.py::test_canonical_url_drops_tracking_and_trailing_slash[https://a.example/jobs/1-https://a.example/jobs/1]` | PASSED | 0.810 |
| 184 | `tests/test_discovery_dedupe.py::test_canonical_url_drops_tracking_and_trailing_slash[https://a.example/jobs/1/-https://a.example/jobs/1]` | PASSED | 0.736 |
| 185 | `tests/test_discovery_dedupe.py::test_canonical_url_drops_tracking_and_trailing_slash[https://A.example/jobs/1-https://a.example/jobs/1]` | PASSED | 0.809 |
| 186 | `tests/test_discovery_dedupe.py::test_canonical_url_drops_tracking_and_trailing_slash[https://a.example/jobs/1?utm_source=x&utm_medium=y&gh_src=abc&ref=z-https://a.example/jobs/1]` | PASSED | 0.777 |
| 187 | `tests/test_discovery_dedupe.py::test_canonical_url_drops_tracking_and_trailing_slash[https://a.example/jobs/1?dept=eng&utm_campaign=q-https://a.example/jobs/1?dept=eng]` | PASSED | 0.752 |
| 188 | `tests/test_discovery_dedupe.py::test_canonical_url_drops_tracking_and_trailing_slash[https://a.example/jobs/1#apply-https://a.example/jobs/1]` | PASSED | 0.775 |
| 189 | `tests/test_discovery_dedupe.py::test_normalize_stores_canonical_url` | PASSED | 0.758 |
| 190 | `tests/test_discovery_dedupe.py::test_fingerprint_ignores_case_punctuation_and_trailing_city` | PASSED | 0.813 |
| 191 | `tests/test_discovery_dedupe.py::test_fingerprint_differs_on_employment_type` | PASSED | 0.677 |
| 192 | `tests/test_discovery_dedupe.py::test_canonical_url_match_links_duplicate_without_deleting` | PASSED | 0.701 |
| 193 | `tests/test_discovery_dedupe.py::test_cross_source_fingerprint_links_duplicate` | PASSED | 0.593 |
| 194 | `tests/test_discovery_dedupe.py::test_fuzzy_match_requires_same_company_and_city` | PASSED | 0.653 |
| 195 | `tests/test_discovery_dedupe.py::test_duplicate_chain_resolves_to_the_canonical_job` | PASSED | 0.843 |
| 196 | `tests/test_discovery_dedupe.py::test_run_rerun_is_idempotent_and_keeps_duplicate_links` | PASSED | 1.487 |
| 197 | `tests/test_discovery_dedupe.py::test_closed_jobs_stay_stored_and_are_not_duplicate_targets` | PASSED | 1.224 |
| 198 | `tests/test_discovery_dedupe.py::test_ashby_board_still_normalizes_after_dedupe_fields` | PASSED | 1.274 |
| 199 | `tests/test_doctor.py::test_doctor_reports_environment` | PASSED | 0.846 |
| 200 | `tests/test_doctor.py::test_doctor_without_config_reports_error` | PASSED | 0.721 |
| 201 | `tests/test_ingest.py::test_upload_stores_content_addressed_file` | PASSED | 0.864 |
| 202 | `tests/test_ingest.py::test_upload_same_file_is_deduplicated` | PASSED | 0.894 |
| 203 | `tests/test_ingest.py::test_upload_different_file_supersedes_and_keeps_old_file` | PASSED | 0.917 |
| 204 | `tests/test_ingest.py::test_download_returns_original_bytes` | PASSED | 0.887 |
| 205 | `tests/test_ingest.py::test_upload_without_csrf_is_rejected` | PASSED | 0.736 |
| 206 | `tests/test_ingest.py::test_unsupported_extension_rejected` | PASSED | 0.787 |
| 207 | `tests/test_ingest.py::test_pdf_magic_bytes_enforced` | PASSED | 1.059 |
| 208 | `tests/test_ingest.py::test_size_cap_enforced` | PASSED | 0.869 |
| 209 | `tests/test_ingest.py::test_encrypted_pdf_rejected` | PASSED | 1.068 |
| 210 | `tests/test_ingest.py::test_page_cap_enforced` | PASSED | 0.888 |
| 211 | `tests/test_ingest.py::test_zip_bomb_docx_rejected` | PASSED | 1.761 |
| 212 | `tests/test_ingest.py::test_pdf_locators_use_page_and_block` | PASSED | 1.114 |
| 213 | `tests/test_ingest.py::test_docx_locators_cover_paragraphs_and_tables` | PASSED | 1.476 |
| 214 | `tests/test_ingest.py::test_text_locators_use_line_numbers` | PASSED | 0.699 |
| 215 | `tests/test_ingest.py::test_quote_matcher_normalises_whitespace_and_width` | PASSED | 0.731 |
| 216 | `tests/test_ingest.py::test_failed_validation_writes_nothing` | PASSED | 0.803 |
| 217 | `tests/test_live_9router.py::test_live_guard_rejects_development_schema_before_provider_or_write` | PASSED | 0.618 |
| 218 | `tests/test_live_9router.py::test_live_9router_extraction` | SKIPPED | 0.000 |
| 219 | `tests/test_llm.py::test_returns_validated_object` | PASSED | 0.600 |
| 220 | `tests/test_llm.py::test_repairs_invalid_json_once` | PASSED | 0.659 |
| 221 | `tests/test_llm.py::test_invalid_json_after_repair_fails` | PASSED | 0.943 |
| 222 | `tests/test_llm.py::test_schema_failure_rejects_output` | PASSED | 0.942 |
| 223 | `tests/test_llm.py::test_temperature_outside_role_range_fails` | PASSED | 0.780 |
| 224 | `tests/test_llm.py::test_consent_required_before_call` | PASSED | 0.794 |
| 225 | `tests/test_llm.py::test_consent_allows_call_and_records_metadata` | PASSED | 0.781 |
| 226 | `tests/test_llm.py::test_revoked_consent_blocks_provider_call` | PASSED | 0.770 |
| 227 | `tests/test_llm.py::test_expired_consent_text_blocks_provider_call` | PASSED | 0.744 |
| 228 | `tests/test_llm.py::test_injection_pattern_is_flagged` | PASSED | 0.777 |
| 229 | `tests/test_llm.py::test_no_network_used` | PASSED | 0.715 |
| 230 | `tests/test_profile.py::test_fake_provider_produces_profile_with_evidence` | PASSED | 0.832 |
| 231 | `tests/test_profile.py::test_zero_facts_without_evidence` | PASSED | 0.820 |
| 232 | `tests/test_profile.py::test_evidence_quotes_exist_in_source` | PASSED | 0.835 |
| 233 | `tests/test_profile.py::test_fake_provider_never_calls_network` | PASSED | 0.743 |
| 234 | `tests/test_profile.py::test_reupload_detects_conflict` | PASSED | 1.422 |
| 235 | `tests/test_profile.py::test_confirm_blocked_while_conflicts_unresolved` | PASSED | 1.406 |
| 236 | `tests/test_profile.py::test_conflict_resolution_then_confirm` | PASSED | 1.165 |
| 237 | `tests/test_profile.py::test_correction_requires_matching_version` | PASSED | 1.070 |
| 238 | `tests/test_profile.py::test_correction_on_confirmed_creates_new_draft` | PASSED | 1.168 |
| 239 | `tests/test_profile.py::test_rollback_moves_active_pointer_without_new_version` | PASSED | 1.206 |
| 240 | `tests/test_profile.py::test_rollback_rejects_unconfirmed_target` | PASSED | 1.232 |
| 241 | `tests/test_profile.py::test_discovery_gate_stays_locked_until_confirmed` | PASSED | 1.056 |
| 242 | `tests/test_profile.py::test_master_cv_unchanged_after_profile_edit` | PASSED | 0.948 |
| 243 | `tests/test_profile.py::test_extraction_requires_master_cv` | PASSED | 0.954 |
| 244 | `tests/test_project_rules.py::test_single_ui_library` | PASSED | 0.701 |
| 245 | `tests/test_project_rules.py::test_dependencies_are_exactly_pinned` | PASSED | 0.686 |
| 246 | `tests/test_project_rules.py::test_css_exceptions_only` | PASSED | 0.776 |
| 247 | `tests/test_project_rules.py::test_no_server_side_html_templates` | PASSED | 0.755 |
| 248 | `tests/test_project_rules.py::test_no_real_provider_or_model_assumed` | PASSED | 0.900 |
| 249 | `tests/test_provider_integration.py::test_extraction_is_blocked_without_consent` | PASSED | 0.876 |
| 250 | `tests/test_provider_integration.py::test_consent_scope_is_provider_model_and_data_classes` | PASSED | 0.802 |
| 251 | `tests/test_provider_integration.py::test_adapter_sends_configured_model_and_never_invents_a_provider` | PASSED | 0.675 |
| 252 | `tests/test_provider_integration.py::test_api_key_comes_from_env_only_when_configured` | PASSED | 0.738 |
| 253 | `tests/test_provider_integration.py::test_provider_failure_never_exposes_the_api_key` | PASSED | 1.026 |
| 254 | `tests/test_provider_integration.py::test_active_provider_selects_the_configured_provider` | PASSED | 0.773 |
| 255 | `tests/test_provider_integration.py::test_evidence_and_quotes_trace_to_the_synthetic_source` | PASSED | 0.812 |
| 256 | `tests/test_provider_integration.py::test_prompt_hash_and_metadata_are_reproducible` | PASSED | 0.870 |
| 257 | `tests/test_provider_integration.py::test_prompt_hash_changes_with_source_text` | PASSED | 0.701 |
| 258 | `tests/test_provider_integration.py::test_log_has_metadata_only` | PASSED | 0.731 |
| 259 | `tests/test_provider_integration.py::test_provider_error_does_not_fall_back` | PASSED | 0.841 |
| 260 | `tests/test_provider_integration.py::test_retryable_error_retries_same_provider_only` | PASSED | 0.799 |
| 261 | `tests/test_provider_integration.py::test_single_active_provider_is_the_only_one_constructed` | PASSED | 0.703 |
| 262 | `tests/test_redact.py::test_redacts_email_and_phone` | PASSED | 0.755 |
| 263 | `tests/test_redact.py::test_redacts_url_query` | PASSED | 0.725 |
| 264 | `tests/test_redact.py::test_redacts_secret_assignment` | PASSED | 0.827 |
| 265 | `tests/test_settings_consent.py::test_get_consent_requires_consent` | PASSED | 0.883 |
| 266 | `tests/test_settings_consent.py::test_grant_and_read_consent` | PASSED | 0.889 |
| 267 | `tests/test_settings_consent.py::test_client_cannot_set_text_version` | PASSED | 0.840 |
| 268 | `tests/test_settings_consent.py::test_grant_rejects_wrong_scope` | PASSED | 0.924 |
| 269 | `tests/test_settings_consent.py::test_revoke_consent` | PASSED | 0.864 |
| 270 | `tests/test_settings_consent.py::test_revoke_unknown_consent_is_404` | PASSED | 0.901 |
| 271 | `tests/test_settings_consent.py::test_history_limit_is_validated` | PASSED | 0.915 |
| 272 | `tests/test_settings_consent.py::test_expired_text_version_requires_new_consent` | PASSED | 0.982 |
| 273 | `tests/test_settings_consent.py::test_extraction_without_consent_is_blocked` | PASSED | 1.031 |
| 274 | `tests/test_sources.py::test_new_source_is_unverified_and_disabled` | PASSED | 0.949 |
| 275 | `tests/test_sources.py::test_unverified_source_cannot_be_enabled` | PASSED | 0.941 |
| 276 | `tests/test_sources.py::test_verify_then_enable_and_disable` | PASSED | 0.926 |
| 277 | `tests/test_sources.py::test_edit_changes_company_and_careers_url` | PASSED | 0.859 |
| 278 | `tests/test_sources.py::test_ats_must_match_careers_url_host_on_create` | PASSED | 0.821 |
| 279 | `tests/test_sources.py::test_ats_must_match_careers_url_host_on_update` | PASSED | 0.996 |
| 280 | `tests/test_sources.py::test_ats_api_requires_a_known_adapter` | PASSED | 0.843 |
| 281 | `tests/test_sources.py::test_html_source_may_stay_unverified_without_an_adapter` | PASSED | 0.912 |
| 282 | `tests/test_sources.py::test_broken_or_restricted_source_cannot_stay_enabled` | PASSED | 0.953 |
| 283 | `tests/test_sources.py::test_insecure_careers_url_is_rejected` | PASSED | 0.877 |
| 284 | `tests/test_sources.py::test_manual_url_is_not_user_managed` | PASSED | 0.898 |
| 285 | `tests/test_sources.py::test_list_filters_and_pagination` | PASSED | 1.095 |
| 286 | `tests/test_url_guard.py::test_accepts_public_https` | PASSED | 0.802 |
| 287 | `tests/test_url_guard.py::test_rejects_unsafe_urls[http://example.com/jobs]` | PASSED | 0.704 |
| 288 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://user:pass@example.com/jobs]` | PASSED | 0.741 |
| 289 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://127.0.0.1/jobs]` | PASSED | 0.774 |
| 290 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://10.0.0.5/jobs]` | PASSED | 0.792 |
| 291 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://192.168.1.10/jobs]` | PASSED | 0.792 |
| 292 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://169.254.169.254/latest/meta-data]` | PASSED | 0.857 |
| 293 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://localhost/jobs]` | PASSED | 0.738 |
| 294 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://metadata.google.internal/computeMetadata/v1]` | PASSED | 0.795 |
| 295 | `tests/test_url_guard.py::test_rejects_unsafe_urls[https://example.com:8080/jobs]` | PASSED | 0.863 |
| 296 | `tests/test_url_guard.py::test_rejects_hostname_resolving_to_private` | PASSED | 0.787 |
| 297 | `tests/test_url_guard.py::test_rejects_too_many_redirects` | PASSED | 0.781 |
| 298 | `tests/test_url_guard.py::test_validates_every_redirect` | PASSED | 1.017 |

## Skipped details

- `tests/test_live_9router.py::test_live_9router_extraction`: live provider test is opt-in: set GAWE_LIVE_9ROUTER=1 and point GAWE_LIVE_CONFIG at a config whose active_provider is 9Router

## Failure details

None. No test failed or errored.

---

## Gap-closing 3D (2026-10-21)

### Backend suite

- Command: `backend\.venv\Scripts\python.exe -m pytest backend/tests -o addopts="" -q -p no:warnings`
- Result: `334 passed, 1 skipped in 69.30s (0:01:08)`
- Skipped: `backend/tests/test_live_9router.py` (opt-in live provider; unchanged reason)
- Change vs previous run: 317 -> 334 passed. New: `tests/test_export.py` (12), `tests/test_reviewer_seeded_defects.py` (3), 2 frontend-unrelated; schema assertions now derive from the latest migration file instead of a hardcoded name.

### Focused runs during the work

- `backend\tests\test_export.py` alone: `12 passed in 14.90s` (includes real Tectonic PDF: CV 1 page, cover letter 1 page).
- `backend\tests\test_db.py backend\tests\test_api.py backend\tests\test_doctor.py`: `27 passed in 5.05s`.
- `temporary/check_seeded.py`: `misses: 0` (all 11 seeded defects detected).

### Frontend

- Command: `cd frontend; npx vitest run`
- Result: `Test Files 7 passed (7)`, `Tests 41 passed (41)` in ~5.5 s.
- Command: `cd frontend; npx tsc --noEmit` -> no output (clean).
- Command: `cd frontend; npm run build` -> `999 modules transformed`, `built in 1.24s`; warning only: chunk > 500 kB.

### Live run (real network, no mocks)

- Command: `backend\.venv\Scripts\python.exe temporary\live_phase3.py`
- Log: `temporary/live-phase3-run.log`
- Result: `failures: 0`
- Schema: throwaway `gawe_test_live_*`; dropped after the run. Fake provider used only for profile extraction; discovery, parsing, eligibility, PDF, and export ran live.
- Discovery: 3 verified+enabled global sources -> GitLab/Greenhouse 232 jobs, Binance/Lever 17, Linear/Ashby 29. 259 jobs assessed: 116 `eligible`, 125 `needs_review`, 18 `ineligible`.
- URL 1 (discovery, Greenhouse): `https://job-boards.greenhouse.io/gitlab/jobs/8877428002` -> workspace, CV + cover letter, review, approval, export; CV 1 page (16.3 KB), CL 1 page (11.8 KB), both downloaded as real PDF.
- URL 2 (discovery, Ashby): `https://jobs.ashbyhq.com/linear/0c7c2e26-0a98-42cf-a47c-9a3999fb513b` -> same full chain, PDF 1 page each.
- URL 3 (manual fallback): a Stripe job page from a board that is not in the registry -> `manual_url` synthetic source, job parsed with title/company, eligibility computed. Documents blocked because eligibility is `needs_review`, which is the correct product rule.
- Redirect handling: `boards.greenhouse.io` -> `job-boards.greenhouse.io` now allowed when both hosts share a registrable domain; every redirect is still re-validated by the URL guard.

### Limitations of this evidence

- No manual UI test; UI behaviour is covered by component tests only.
- Draft content quality has no human review yet.
- `D9` (separate reviewer model) is not implemented; the reviewer is deterministic.
- Indonesian sources are inactive (D17 + ToS/attribution).
- HTML adapter for registry `html` sources and scheduled discovery runs are not implemented; they are outside the 3A-3D acceptance list.
- Acceptance 3A-3D is not marked passed until the user approves the §11 gate.
