-- Phase 4: source priority, schedule, quota, and health state.
-- Statements are idempotent so a partially applied migration can be re-run.

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'priority_order'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN priority_order INT NOT NULL DEFAULT 100'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'fetch_interval_minutes'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN fetch_interval_minutes INT NOT NULL DEFAULT 360'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'daily_request_quota'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN daily_request_quota INT NOT NULL DEFAULT 24'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'next_run_at'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN next_run_at VARCHAR(32) NULL'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'health_status'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN health_status VARCHAR(32) NOT NULL DEFAULT ''unknown'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'consecutive_failures'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN consecutive_failures INT NOT NULL DEFAULT 0'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'last_success_at'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN last_success_at VARCHAR(32) NULL'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND COLUMN_NAME = 'last_error_code'
    ),
    'SELECT 1',
    'ALTER TABLE source_registry ADD COLUMN last_error_code VARCHAR(64) NULL'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- The scheduler asks "which enabled sources are due", ordered by priority.
SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_registry'
          AND INDEX_NAME = 'idx_source_registry_due'
    ),
    'SELECT 1',
    'CREATE INDEX idx_source_registry_due ON source_registry (enabled, verification_status, next_run_at, priority_order)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- The daily quota counts attempts, not stored fetches: a 304 writes no
-- `source_fetch` row but still spends a request.
SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'discovery_run_source'
          AND INDEX_NAME = 'idx_run_source_quota'
    ),
    'SELECT 1',
    'CREATE INDEX idx_run_source_quota ON discovery_run_source (source_id, last_attempt_at)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Job Matches filters run in SQL. Without these, every filter was a full scan of
-- `job` joined with the assessments.
SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND INDEX_NAME = 'idx_job_matches'
    ),
    'SELECT 1',
    'CREATE INDEX idx_job_matches ON job (status, duplicate_of, market, work_mode, priority_tier)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'eligibility_assessment'
          AND INDEX_NAME = 'idx_eligibility_profile_status'
    ),
    'SELECT 1',
    'CREATE INDEX idx_eligibility_profile_status ON eligibility_assessment (profile_version_id, status)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- `posted_at` is an ISO string, so sorting by it in SQL meant parsing every row.
-- The epoch is written once, at job write time.
SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'posted_at_epoch'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN posted_at_epoch BIGINT NOT NULL DEFAULT 0'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Backfill rows written before the column existed. `posted_at` is a UTC ISO
-- string; the conversion is monotonic, so sort order stays correct.
UPDATE job
SET posted_at_epoch = UNIX_TIMESTAMP(STR_TO_DATE(LEFT(posted_at, 19), '%Y-%m-%dT%H:%i:%s'))
WHERE posted_at_epoch = 0
  AND posted_at IS NOT NULL
  AND posted_at <> '';

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND INDEX_NAME = 'idx_job_posted_epoch'
    ),
    'SELECT 1',
    'CREATE INDEX idx_job_posted_epoch ON job (posted_at_epoch DESC)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Ranking order as rows. `sections_json` stays the auditable snapshot; this table
-- exists so `/api/matches` can order and page in SQL instead of loading every
-- match into memory. `position` is the rank inside the section, so a keyset scan
-- on (ranking_run_id, section, position, job_id) is enough.
CREATE TABLE IF NOT EXISTS job_rank (
    ranking_run_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    section VARCHAR(32) NOT NULL,
    position INT NOT NULL,
    PRIMARY KEY (ranking_run_id, job_id),
    KEY idx_job_rank_order (ranking_run_id, section, position, job_id),
    CONSTRAINT fk_job_rank_run
        FOREIGN KEY (ranking_run_id) REFERENCES ranking_run (ranking_run_id),
    CONSTRAINT fk_job_rank_job
        FOREIGN KEY (job_id) REFERENCES job (job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
