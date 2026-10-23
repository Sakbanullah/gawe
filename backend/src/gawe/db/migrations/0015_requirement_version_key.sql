-- Phase 3: requirement identity belongs to one job posting version.
--
-- `requirement_id` hashes category and normalised text, so two jobs that state
-- the same requirement produce the same id. With `requirement_id` alone as the
-- primary key, the second job's INSERT hit the duplicate branch of
-- `ON DUPLICATE KEY UPDATE`, which does not rewrite `job_posting_version_id`.
-- The row stayed with the first version, so the second job had no requirement
-- rows: its match detail showed none, and a reassessment read a partial set.
--
-- Idempotent so a partially applied migration can be re-run.
SET @sql = IF(
EXISTS(
SELECT 1 FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'job_requirement'
AND INDEX_NAME = 'PRIMARY'
AND COLUMN_NAME = 'job_posting_version_id'
),
'SELECT 1',
'ALTER TABLE job_requirement DROP PRIMARY KEY, ADD PRIMARY KEY (job_posting_version_id, requirement_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
