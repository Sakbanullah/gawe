-- Phase 2A (MySQL 8): Master CV store, immutable profile versions, in-process tasks.
-- Statements are idempotent so a partially applied migration can be re-run.

CREATE TABLE IF NOT EXISTS master_cv (
    master_cv_id VARCHAR(64) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    mime VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    page_count INT NULL,
    status VARCHAR(32) NOT NULL,
    active_profile_version_id VARCHAR(64) NULL,
    extraction_task_id VARCHAR(64) NULL,
    uploaded_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (master_cv_id),
    UNIQUE KEY uq_master_cv_sha256 (sha256),
    KEY idx_master_cv_uploaded (uploaded_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS source_document (
    doc_id VARCHAR(64) NOT NULL,
    master_cv_id VARCHAR(64) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    mime VARCHAR(128) NOT NULL,
    page_count INT NULL,
    blocks_json LONGTEXT NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (doc_id),
    KEY idx_source_document_master_cv (master_cv_id),
    CONSTRAINT fk_source_document_master_cv
        FOREIGN KEY (master_cv_id) REFERENCES master_cv (master_cv_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS profile_version (
    profile_version_id VARCHAR(64) NOT NULL,
    profile_id VARCHAR(64) NOT NULL,
    master_cv_id VARCHAR(64) NOT NULL,
    derived_from_profile_version_id VARCHAR(64) NULL,
    version INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    content_json LONGTEXT NOT NULL,
    evidence_json LONGTEXT NOT NULL,
    conflicts_json LONGTEXT NOT NULL,
    active TINYINT NOT NULL DEFAULT 0,
    -- Generated key keeps the SQLite partial unique index semantics: at most
    -- one active row, unlimited inactive rows.
    active_key TINYINT GENERATED ALWAYS AS (IF(active = 1, 1, NULL)) STORED,
    confirmed_at VARCHAR(32) NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (profile_version_id),
    UNIQUE KEY uq_profile_version_number (profile_id, version),
    UNIQUE KEY uq_profile_version_active (active_key),
    KEY idx_profile_version_created (created_at DESC),
    KEY idx_profile_version_master_cv (master_cv_id),
    CONSTRAINT fk_profile_version_master_cv
        FOREIGN KEY (master_cv_id) REFERENCES master_cv (master_cv_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS profile_correction (
    correction_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    `path` VARCHAR(255) NOT NULL,
    old_value_json LONGTEXT NULL,
    new_value_json LONGTEXT NOT NULL,
    reason TEXT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (correction_id),
    KEY idx_profile_correction_version (profile_version_id),
    CONSTRAINT fk_profile_correction_version
        FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS profile_decision (
    decision_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NULL,
    action VARCHAR(64) NOT NULL,
    reason TEXT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (decision_id),
    KEY idx_profile_decision_version (profile_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS task (
    task_id VARCHAR(64) NOT NULL,
    type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    application_id VARCHAR(64) NULL,
    progress_json LONGTEXT NOT NULL,
    result_json LONGTEXT NULL,
    error_json LONGTEXT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    finished_at VARCHAR(32) NULL,
    PRIMARY KEY (task_id),
    KEY idx_task_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
