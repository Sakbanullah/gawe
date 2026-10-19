-- Phase 1 initial schema (MySQL 8): only tables the foundation uses.
-- Full domain DDL stays OPEN (DATABASE.md §9); later migrations add it.
-- Statements are idempotent so a partially applied migration can be re-run.

CREATE TABLE IF NOT EXISTS schema_version (
    version VARCHAR(64) NOT NULL,
    applied_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS consent_record (
    consent_id VARCHAR(64) NOT NULL,
    consent_type VARCHAR(64) NOT NULL,
    provider_id VARCHAR(128) NOT NULL,
    model_snapshot LONGTEXT NOT NULL,
    text LONGTEXT NOT NULL,
    granted_at VARCHAR(32) NOT NULL,
    revoked_at VARCHAR(32) NULL,
    PRIMARY KEY (consent_id),
    KEY idx_consent_granted (granted_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS llm_call (
    call_id VARCHAR(64) NOT NULL,
    run_id VARCHAR(64) NULL,
    role VARCHAR(32) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(128) NOT NULL,
    prompt_id VARCHAR(64) NOT NULL,
    prompt_hash CHAR(64) NOT NULL,
    response_hash CHAR(64) NOT NULL,
    input_tokens INT NULL,
    output_tokens INT NULL,
    cost_usd DOUBLE NULL,
    latency_ms INT NOT NULL,
    attempt INT NOT NULL,
    repaired TINYINT NOT NULL,
    error_code VARCHAR(64) NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (call_id),
    KEY idx_llm_call_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
