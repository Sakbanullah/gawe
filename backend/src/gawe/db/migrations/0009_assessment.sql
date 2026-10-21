-- Phase 3C: priority tier snapshot, requirements, eligibility, fit, ranking.
-- Every ADD COLUMN / ADD KEY is guarded so a partially applied migration can be
-- re-run; the runner records the version only after every statement succeeds.

CREATE TABLE IF NOT EXISTS job_requirement (
    requirement_id VARCHAR(64) NOT NULL,
    job_posting_version_id VARCHAR(64) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    category VARCHAR(32) NOT NULL,
    text VARCHAR(2000) NOT NULL,
    quote VARCHAR(2000) NOT NULL,
    weight DECIMAL(4,2) NOT NULL DEFAULT 1.00,
    constraint_json LONGTEXT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (requirement_id),
    KEY idx_job_requirement_version (job_posting_version_id),
    CONSTRAINT fk_job_requirement_version
        FOREIGN KEY (job_posting_version_id)
        REFERENCES job_posting_version (job_posting_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS eligibility_assessment (
    assessment_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    job_posting_version_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    checks_json LONGTEXT NOT NULL,
    reason_summary VARCHAR(500) NULL,
    confidence VARCHAR(16) NOT NULL,
    status_outdated TINYINT NOT NULL DEFAULT 0,
    outdated_reason VARCHAR(1000) NULL,
    computed_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (assessment_id),
    UNIQUE KEY uq_eligibility_version_profile (job_posting_version_id, profile_version_id),
    KEY idx_eligibility_job (job_id),
    CONSTRAINT fk_eligibility_job
        FOREIGN KEY (job_id) REFERENCES job (job_id),
    CONSTRAINT fk_eligibility_version
        FOREIGN KEY (job_posting_version_id)
        REFERENCES job_posting_version (job_posting_version_id),
    CONSTRAINT fk_eligibility_profile
        FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS fit_assessment (
    assessment_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    job_posting_version_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    fit_score INT NOT NULL,
    verdict VARCHAR(16) NOT NULL,
    confidence VARCHAR(16) NOT NULL,
    components_json LONGTEXT NOT NULL,
    gaps_json LONGTEXT NOT NULL,
    status_outdated TINYINT NOT NULL DEFAULT 0,
    outdated_reason VARCHAR(1000) NULL,
    computed_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (assessment_id),
    UNIQUE KEY uq_fit_version_profile (job_posting_version_id, profile_version_id),
    KEY idx_fit_job (job_id),
    CONSTRAINT fk_fit_job
        FOREIGN KEY (job_id) REFERENCES job (job_id),
    CONSTRAINT fk_fit_version
        FOREIGN KEY (job_posting_version_id)
        REFERENCES job_posting_version (job_posting_version_id),
    CONSTRAINT fk_fit_profile
        FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ranking_run (
    ranking_run_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    tie_window INT NOT NULL DEFAULT 0,
    primary_key VARCHAR(32) NOT NULL,
    tie_breaker_json LONGTEXT NOT NULL,
    sections_json LONGTEXT NOT NULL,
    counts_json LONGTEXT NOT NULL,
    computed_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (ranking_run_id),
    KEY idx_ranking_run_profile (profile_version_id, computed_at DESC),
    CONSTRAINT fk_ranking_run_profile
        FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'priority_tier'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN priority_tier VARCHAR(32) NOT NULL DEFAULT ''unclassified'' AFTER market'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'priority_reason'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN priority_reason VARCHAR(1000) NULL AFTER priority_tier'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'priority_confidence'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN priority_confidence VARCHAR(16) NOT NULL DEFAULT ''unknown'' AFTER priority_reason'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'priority_tier_override'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN priority_tier_override VARCHAR(32) NULL AFTER priority_confidence'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'priority_tier_override_reason'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN priority_tier_override_reason VARCHAR(1000) NULL AFTER priority_tier_override'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
