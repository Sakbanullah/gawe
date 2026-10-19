-- Phase 2B: versioned consent text and explicit data scope.
-- Existing rows keep empty version/hash, so they are treated as expired and
-- require a fresh consent. Data is never rewritten or dropped here.
-- MySQL 8 has no ADD COLUMN IF NOT EXISTS, so every column is added behind an
-- information_schema check. A re-run after a partial apply (column added but
-- schema_version not recorded) then skips the existing column and continues.

SET @gawe_ddl = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'consent_record'
       AND column_name = 'text_version') = 0,
    'ALTER TABLE consent_record ADD COLUMN text_version VARCHAR(100) NOT NULL DEFAULT ''''',
    'DO 0'
);
PREPARE gawe_stmt FROM @gawe_ddl;
EXECUTE gawe_stmt;
DEALLOCATE PREPARE gawe_stmt;

SET @gawe_ddl = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'consent_record'
       AND column_name = 'text_sha256') = 0,
    'ALTER TABLE consent_record ADD COLUMN text_sha256 CHAR(64) NOT NULL DEFAULT ''''',
    'DO 0'
);
PREPARE gawe_stmt FROM @gawe_ddl;
EXECUTE gawe_stmt;
DEALLOCATE PREPARE gawe_stmt;

SET @gawe_ddl = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'consent_record'
       AND column_name = 'data_classes_json') = 0,
    'ALTER TABLE consent_record ADD COLUMN data_classes_json LONGTEXT NULL',
    'DO 0'
);
PREPARE gawe_stmt FROM @gawe_ddl;
EXECUTE gawe_stmt;
DEALLOCATE PREPARE gawe_stmt;
