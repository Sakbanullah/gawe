-- Phase 3D: the document adjustment plan the user approves before any document
-- is written.
--
-- The plan is bound to the posting version and profile version it was built
-- from, so a re-import or a new profile makes it `outdated` instead of silently
-- applying stale reasoning. Approval is recorded in its own table: approving a
-- plan never approves a document, and cloud consent stays separate.
--
-- `plan_json` holds candidate data. It is never logged; only ids, version,
-- hash, and status are metadata.

CREATE TABLE IF NOT EXISTS document_plan (
    plan_id VARCHAR(64) NOT NULL,
    application_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    job_posting_version_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    version INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    plan_json LONGTEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (plan_id),
    UNIQUE KEY uq_document_plan_version (application_id, version),
    UNIQUE KEY uq_document_plan_hash (application_id, content_hash),
    KEY idx_document_plan_latest (application_id, created_at DESC),
    CONSTRAINT fk_document_plan_application
        FOREIGN KEY (application_id) REFERENCES application (application_id),
    CONSTRAINT fk_document_plan_job_posting
        FOREIGN KEY (job_posting_version_id)
        REFERENCES job_posting_version (job_posting_version_id),
    CONSTRAINT fk_document_plan_profile
        FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS document_plan_approval (
    approval_id VARCHAR(64) NOT NULL,
    plan_id VARCHAR(64) NOT NULL,
    application_id VARCHAR(64) NOT NULL,
    plan_hash CHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    note TEXT NULL,
    decided_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (approval_id),
    UNIQUE KEY uq_document_plan_approval (plan_id, plan_hash, decision),
    KEY idx_document_plan_approval_plan (plan_id, decided_at DESC),
    CONSTRAINT fk_document_plan_approval_plan
        FOREIGN KEY (plan_id) REFERENCES document_plan (plan_id),
    CONSTRAINT fk_document_plan_approval_application
        FOREIGN KEY (application_id) REFERENCES application (application_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Which plan a document version was written from. Nullable: versions created
-- before this migration have no plan, and a revision of an old version keeps
-- the null instead of inventing one.
SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'document_version'
          AND COLUMN_NAME = 'plan_id'
    ),
    'SELECT 1',
    'ALTER TABLE document_version ADD COLUMN plan_id VARCHAR(64) NULL AFTER template_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
