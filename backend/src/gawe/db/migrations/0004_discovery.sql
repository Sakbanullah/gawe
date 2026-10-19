-- Phase 3A (MySQL 8): source registry, discovery runs, raw fetch evidence, jobs.
-- Statements are idempotent so a partially applied migration can be re-run.

CREATE TABLE IF NOT EXISTS source_registry (
    source_id VARCHAR(64) NOT NULL,
    company VARCHAR(200) NOT NULL,
    market VARCHAR(32) NOT NULL,
    careers_url VARCHAR(2048) NOT NULL,
    access_method VARCHAR(32) NOT NULL,
    ats VARCHAR(32) NOT NULL,
    verification_status VARCHAR(32) NOT NULL,
    tos_notes TEXT NULL,
    last_checked_at VARCHAR(32) NULL,
    enabled TINYINT NOT NULL DEFAULT 0,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (source_id),
    KEY idx_source_registry_enabled (enabled, verification_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS discovery_run (
    run_id VARCHAR(64) NOT NULL,
    task_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    counts_json LONGTEXT NOT NULL,
    error_json LONGTEXT NULL,
    started_at VARCHAR(32) NOT NULL,
    finished_at VARCHAR(32) NULL,
    PRIMARY KEY (run_id),
    KEY idx_discovery_run_started (started_at DESC),
    KEY idx_discovery_run_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS discovery_run_source (
    run_id VARCHAR(64) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    company VARCHAR(200) NOT NULL,
    status VARCHAR(32) NOT NULL,
    fetched_count INT NOT NULL DEFAULT 0,
    accepted_count INT NOT NULL DEFAULT 0,
    duplicate_count INT NOT NULL DEFAULT 0,
    retry_count INT NOT NULL DEFAULT 0,
    last_attempt_at VARCHAR(32) NULL,
    error_json LONGTEXT NULL,
    PRIMARY KEY (run_id, source_id),
    CONSTRAINT fk_discovery_run_source_run
        FOREIGN KEY (run_id) REFERENCES discovery_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS source_fetch (
    fetch_id VARCHAR(64) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    http_status INT NULL,
    fetched_at VARCHAR(32) NOT NULL,
    raw_sha256 CHAR(64) NOT NULL,
    raw_json LONGTEXT NOT NULL,
    error_json LONGTEXT NULL,
    PRIMARY KEY (fetch_id),
    KEY idx_source_fetch_run (run_id),
    CONSTRAINT fk_source_fetch_run
        FOREIGN KEY (run_id) REFERENCES discovery_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS job (
    job_id VARCHAR(64) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    source_job_id VARCHAR(255) NOT NULL,
    canonical_url VARCHAR(2048) NOT NULL,
    apply_url VARCHAR(2048) NULL,
    company VARCHAR(300) NOT NULL,
    title VARCHAR(300) NOT NULL,
    location_json LONGTEXT NOT NULL,
    work_mode VARCHAR(32) NOT NULL,
    employment_type VARCHAR(32) NOT NULL,
    seniority VARCHAR(32) NOT NULL,
    market VARCHAR(32) NOT NULL,
    posted_at VARCHAR(32) NULL,
    fetched_at VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    duplicate_of VARCHAR(64) NULL,
    latest_version_id VARCHAR(64) NULL,
    completeness_json LONGTEXT NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (job_id),
    UNIQUE KEY uq_job_source_ref (source_id, source_job_id),
    KEY idx_job_canonical_url (canonical_url(191)),
    KEY idx_job_fetched (fetched_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS job_posting_version (
    job_posting_version_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    description_text LONGTEXT NOT NULL,
    raw_sha256 CHAR(64) NOT NULL,
    fetched_at VARCHAR(32) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (job_posting_version_id),
    UNIQUE KEY uq_job_posting_version_hash (job_id, content_hash),
    KEY idx_job_posting_version_job (job_id),
    CONSTRAINT fk_job_posting_version_job
        FOREIGN KEY (job_id) REFERENCES job (job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
