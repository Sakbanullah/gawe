-- Phase 3A: retry bookkeeping for tasks (API-CONTRACTS.md §4.3 RetryInfo).

ALTER TABLE task
    ADD COLUMN attempt INT NOT NULL DEFAULT 1,
    ADD COLUMN retried_from_task_id VARCHAR(64) NULL;
