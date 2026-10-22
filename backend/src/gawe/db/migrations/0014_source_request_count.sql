-- Phase 5: the daily quota counts HTTP requests, not run attempts.
--
-- `requests_24h` was `COUNT(*)` over `discovery_run_source`. That holds only
-- while every adapter spends exactly one request per run. A paginated source
-- spends one request per page, so the quota needs the real number.
--
-- `request_count` is written for every attempt, including a 304 and a failure:
-- a request that failed still cost a request. Rows written before this column
-- existed default to 1, which is what they really spent. A skipped source is
-- never counted, because its `last_attempt_at` stays NULL.
--
-- Statements are idempotent so a partially applied migration can be re-run.

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'discovery_run_source'
          AND COLUMN_NAME = 'request_count'
    ),
    'SELECT 1',
    'ALTER TABLE discovery_run_source ADD COLUMN request_count INT NOT NULL DEFAULT 1 AFTER retry_count'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
