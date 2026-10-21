-- Phase 3D: application workspace per job. One workspace per job_id.
-- Documents, approvals, and exports get their own tables in a later migration.

CREATE TABLE IF NOT EXISTS application (
    application_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (application_id),
    UNIQUE KEY uq_application_job (job_id),
    KEY idx_application_created (created_at DESC),
    CONSTRAINT fk_application_job
        FOREIGN KEY (job_id) REFERENCES job (job_id),
    CONSTRAINT fk_application_profile
        FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
