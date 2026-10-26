-- Phase 3D follow-up: cancel an application workspace without deleting it.
--
-- The record must survive: an approval is bound to a document_version_id and
-- its content_hash, so removing the row would cut the audit trail. `cancelled_at`
-- is the flag; `_status()` projects "cancelled" from it.

ALTER TABLE application
    ADD COLUMN cancelled_at VARCHAR(32) NULL,
    ADD COLUMN cancel_reason VARCHAR(500) NULL,
    ADD KEY idx_application_cancelled (cancelled_at);
