-- Phase 3D: deterministic document drafts, versions, reviews, and approvals.
-- LaTeX/PDF and export records are out of scope; no column claims them.

CREATE TABLE IF NOT EXISTS document_version (
    document_version_id VARCHAR(64) NOT NULL,
    application_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    job_posting_version_id VARCHAR(64) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    version INT NOT NULL,
    parent_document_version_id VARCHAR(64) NULL,
    status VARCHAR(32) NOT NULL,
    content_json LONGTEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    diff_json LONGTEXT NOT NULL,
    evidence_json LONGTEXT NOT NULL,
    prompt_version VARCHAR(64) NULL,
    template_version VARCHAR(64) NULL,
    provider VARCHAR(64) NULL,
    model VARCHAR(128) NULL,
    review_status VARCHAR(32) NOT NULL DEFAULT 'not_started',
    review_verdict VARCHAR(32) NULL,
    review_cycle INT NULL,
    findings_json LONGTEXT NULL,
    reviewed_at VARCHAR(32) NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (document_version_id),
    UNIQUE KEY uq_document_version_number (application_id, kind, version),
    KEY idx_document_version_app (application_id, created_at DESC),
    CONSTRAINT fk_document_version_application
        FOREIGN KEY (application_id) REFERENCES application (application_id),
    CONSTRAINT fk_document_version_profile
        FOREIGN KEY (profile_version_id) REFERENCES profile_version (profile_version_id),
    CONSTRAINT fk_document_version_job_posting
        FOREIGN KEY (job_posting_version_id)
        REFERENCES job_posting_version (job_posting_version_id),
    CONSTRAINT fk_document_version_parent
        FOREIGN KEY (parent_document_version_id)
        REFERENCES document_version (document_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS document_approval (
    approval_id VARCHAR(64) NOT NULL,
    document_version_id VARCHAR(64) NOT NULL,
    application_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    document_hash CHAR(64) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    note TEXT NULL,
    decided_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (approval_id),
    KEY idx_document_approval_version (document_version_id, decided_at DESC),
    CONSTRAINT fk_document_approval_version
        FOREIGN KEY (document_version_id) REFERENCES document_version (document_version_id),
    CONSTRAINT fk_document_approval_application
        FOREIGN KEY (application_id) REFERENCES application (application_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
