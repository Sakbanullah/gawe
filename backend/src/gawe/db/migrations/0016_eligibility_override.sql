-- Human review outcome for an eligibility assessment.
--
-- `auto_status` keeps what the rules decided. `status` is what the user
-- confirmed after reading the posting, so an override never erases the original
-- result and never hides that a person made the call.

SET @sql = IF(
EXISTS(
SELECT 1 FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'eligibility_assessment'
AND COLUMN_NAME = 'auto_status'
),
'SELECT 1',
'ALTER TABLE eligibility_assessment ADD COLUMN auto_status VARCHAR(32) NULL AFTER status'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
EXISTS(
SELECT 1 FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'eligibility_assessment'
AND COLUMN_NAME = 'override_status'
),
'SELECT 1',
"ALTER TABLE eligibility_assessment ADD COLUMN override_status VARCHAR(32) NULL AFTER auto_status"
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
EXISTS(
SELECT 1 FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'eligibility_assessment'
AND COLUMN_NAME = 'override_reason'
),
'SELECT 1',
'ALTER TABLE eligibility_assessment ADD COLUMN override_reason VARCHAR(1000) NULL AFTER override_status'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
EXISTS(
SELECT 1 FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'eligibility_assessment'
AND COLUMN_NAME = 'overridden_at'
),
'SELECT 1',
'ALTER TABLE eligibility_assessment ADD COLUMN overridden_at VARCHAR(32) NULL AFTER override_reason'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE eligibility_assessment SET auto_status = status WHERE auto_status IS NULL;
