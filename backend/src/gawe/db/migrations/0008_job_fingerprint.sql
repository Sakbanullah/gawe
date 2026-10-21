-- Phase 3B: cross-source fingerprint for deterministic dedupe.
-- The index is what the dedupe lookup uses; it is guarded like every other
-- ALTER in this project so a partially applied migration can be re-run.

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'fingerprint'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN fingerprint CHAR(64) NULL AFTER duplicate_of'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND INDEX_NAME = 'idx_job_fingerprint'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD KEY idx_job_fingerprint (fingerprint)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
