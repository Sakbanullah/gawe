-- Phase 3D: export records for approved document versions.
-- One row per export attempt. `status` follows API-CONTRACTS.md 3.8:
-- exported | tex_only | failed. Only `exported` has a download URL.

CREATE TABLE IF NOT EXISTS export_record (
    export_id VARCHAR(64) NOT NULL,
    application_id VARCHAR(64) NOT NULL,
    document_version_id VARCHAR(64) NOT NULL,
    profile_version_id VARCHAR(64) NOT NULL,
    document_hash CHAR(64) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    filename VARCHAR(200) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    exported_at VARCHAR(32) NULL,
    error_json LONGTEXT NULL,
    download_url VARCHAR(500) NULL,
    pdf_sha256 CHAR(64) NULL,
    qa_json LONGTEXT NULL,
    PRIMARY KEY (export_id),
    KEY idx_export_application (application_id, created_at DESC),
    KEY idx_export_version (document_version_id),
    CONSTRAINT fk_export_application
        FOREIGN KEY (application_id) REFERENCES application (application_id),
    CONSTRAINT fk_export_version
        FOREIGN KEY (document_version_id)
        REFERENCES document_version (document_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
