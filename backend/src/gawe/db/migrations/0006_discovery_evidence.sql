-- Phase 3A: evidence and freshness columns for discovery.
-- Each ADD COLUMN is guarded so a partially applied migration can be re-run.
-- The runner records the version only after every statement succeeds.

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_fetch'
          AND COLUMN_NAME = 'final_url'
    ),
    'SELECT 1',
    'ALTER TABLE source_fetch ADD COLUMN final_url VARCHAR(2048) NULL AFTER error_json'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_fetch'
          AND COLUMN_NAME = 'etag'
    ),
    'SELECT 1',
    'ALTER TABLE source_fetch ADD COLUMN etag VARCHAR(255) NULL AFTER final_url'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_fetch'
          AND COLUMN_NAME = 'last_modified'
    ),
    'SELECT 1',
    'ALTER TABLE source_fetch ADD COLUMN last_modified VARCHAR(255) NULL AFTER etag'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'discovery_run_source'
          AND COLUMN_NAME = 'close_skipped_json'
    ),
    'SELECT 1',
    'ALTER TABLE discovery_run_source ADD COLUMN close_skipped_json LONGTEXT NULL AFTER error_json'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'discovery_run_source'
          AND COLUMN_NAME = 'stats_json'
    ),
    'SELECT 1',
    'ALTER TABLE discovery_run_source ADD COLUMN stats_json LONGTEXT NULL AFTER close_skipped_json'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'description_truncated'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN description_truncated TINYINT NOT NULL DEFAULT 0 AFTER latest_version_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'stale'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN stale TINYINT NOT NULL DEFAULT 0 AFTER description_truncated'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND COLUMN_NAME = 'last_seen_at'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD COLUMN last_seen_at VARCHAR(32) NULL AFTER stale'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
