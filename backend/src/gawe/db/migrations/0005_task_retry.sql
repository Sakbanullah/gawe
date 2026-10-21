-- Phase 3A: retry bookkeeping for tasks (API-CONTRACTS.md §4.3 RetryInfo).
-- Guarded so a partially applied run can be retried without duplicate columns.

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'task'
          AND COLUMN_NAME = 'attempt'
    ),
    'SELECT 1',
    'ALTER TABLE task ADD COLUMN attempt INT NOT NULL DEFAULT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'task'
          AND COLUMN_NAME = 'retried_from_task_id'
    ),
    'SELECT 1',
    'ALTER TABLE task ADD COLUMN retried_from_task_id VARCHAR(64) NULL'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
