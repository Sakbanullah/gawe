-- Phase 3A (D-E): foreign keys that 0004 left to application code.
-- Orphan rows are checked first so the migration fails with a readable name
-- instead of an opaque 1452 halfway through. Every ADD CONSTRAINT is guarded,
-- so a partially applied run can be repeated after cleanup.

SET @orphans = (
    SELECT COUNT(*)
    FROM discovery_run dr
    LEFT JOIN task t ON t.task_id = dr.task_id
    WHERE t.task_id IS NULL
);
SET @sql = IF(
    @orphans = 0,
    'SELECT 1',
    'SELECT 1 FROM `ERROR_orphan_rows_in_discovery_run_task_id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @orphans = (
    SELECT COUNT(*)
    FROM discovery_run dr
    LEFT JOIN profile_version pv ON pv.profile_version_id = dr.profile_version_id
    WHERE pv.profile_version_id IS NULL
);
SET @sql = IF(
    @orphans = 0,
    'SELECT 1',
    'SELECT 1 FROM `ERROR_orphan_rows_in_discovery_run_profile_version_id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @orphans = (
    SELECT COUNT(*)
    FROM discovery_run_source drs
    LEFT JOIN source_registry sr ON sr.source_id = drs.source_id
    WHERE sr.source_id IS NULL
);
SET @sql = IF(
    @orphans = 0,
    'SELECT 1',
    'SELECT 1 FROM `ERROR_orphan_rows_in_discovery_run_source_source_id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @orphans = (
    SELECT COUNT(*)
    FROM source_fetch sf
    LEFT JOIN source_registry sr ON sr.source_id = sf.source_id
    WHERE sr.source_id IS NULL
);
SET @sql = IF(
    @orphans = 0,
    'SELECT 1',
    'SELECT 1 FROM `ERROR_orphan_rows_in_source_fetch_source_id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @orphans = (
    SELECT COUNT(*)
    FROM job j
    LEFT JOIN source_registry sr ON sr.source_id = j.source_id
    WHERE sr.source_id IS NULL
);
SET @sql = IF(
    @orphans = 0,
    'SELECT 1',
    'SELECT 1 FROM `ERROR_orphan_rows_in_job_source_id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'discovery_run'
          AND CONSTRAINT_NAME = 'fk_discovery_run_task'
    ),
    'SELECT 1',
    'ALTER TABLE discovery_run ADD CONSTRAINT fk_discovery_run_task '
    'FOREIGN KEY (task_id) REFERENCES task (task_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'discovery_run'
          AND CONSTRAINT_NAME = 'fk_discovery_run_profile_version'
    ),
    'SELECT 1',
    'ALTER TABLE discovery_run ADD CONSTRAINT fk_discovery_run_profile_version '
    'FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'discovery_run_source'
          AND CONSTRAINT_NAME = 'fk_discovery_run_source_source'
    ),
    'SELECT 1',
    'ALTER TABLE discovery_run_source ADD CONSTRAINT fk_discovery_run_source_source '
    'FOREIGN KEY (source_id) REFERENCES source_registry (source_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'source_fetch'
          AND CONSTRAINT_NAME = 'fk_source_fetch_source'
    ),
    'SELECT 1',
    'ALTER TABLE source_fetch ADD CONSTRAINT fk_source_fetch_source '
    'FOREIGN KEY (source_id) REFERENCES source_registry (source_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'job'
          AND CONSTRAINT_NAME = 'fk_job_source'
    ),
    'SELECT 1',
    'ALTER TABLE job ADD CONSTRAINT fk_job_source '
    'FOREIGN KEY (source_id) REFERENCES source_registry (source_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
