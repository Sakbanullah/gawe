-- Which extractor produced a requirement row.
--
-- The rows double as the per-posting-version cache, so a row that came from the
-- deterministic fallback must not be mistaken for a model reading: the next
-- assessment, possibly with a provider configured, has to be allowed to try
-- again. `regex` is the default so existing rows stay re-readable.

SET @column_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'job_requirement'
      AND COLUMN_NAME = 'source'
);

SET @statement = IF(
    @column_exists = 0,
    'ALTER TABLE job_requirement ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT ''regex''',
    'SELECT 1'
);

PREPARE add_source FROM @statement;
EXECUTE add_source;
DEALLOCATE PREPARE add_source;
