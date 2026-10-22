-- Dead Letter Queue schema and production hardening.
-- Requires the jobs table from scripts/schema.sql or migration 20261022_02.

-- Keep the job context columns required by the worker and DLQ trigger aligned
-- for existing databases as well as new databases.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error_stack TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS worker_id TEXT;

CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    job_type VARCHAR(100) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_error_type VARCHAR(100) NOT NULL,
    final_error_message TEXT,
    final_error_stack TEXT,
    final_attempt_count INTEGER NOT NULL,
    max_retries INTEGER NOT NULL,
    last_worker_id VARCHAR(100),
    last_processed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_reason VARCHAR(100) NOT NULL CHECK (
        archived_reason IN (
            'max_retries_exceeded',
            'permanent_failure',
            'manual_archival',
            'system_cleanup'
        )
    ),
    failure_category VARCHAR(100),
    suggested_fix TEXT,
    resolution_status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (
        resolution_status IN ('pending', 'investigating', 'resolved', 'ignored')
    ),
    resolution_notes TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT dead_letter_queue_original_job_key UNIQUE (original_job_id)
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_archived_at
    ON dead_letter_queue(archived_at);
CREATE INDEX IF NOT EXISTS idx_dead_letter_resolution_status
    ON dead_letter_queue(resolution_status);
CREATE INDEX IF NOT EXISTS idx_dead_letter_failure_category
    ON dead_letter_queue(failure_category);
CREATE INDEX IF NOT EXISTS idx_dead_letter_original_job_id
    ON dead_letter_queue(original_job_id);
CREATE INDEX IF NOT EXISTS idx_dead_letter_created_at
    ON dead_letter_queue(created_at);

CREATE OR REPLACE FUNCTION archive_to_dead_letter_queue()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'failed' AND OLD.status IS DISTINCT FROM 'failed' THEN
        INSERT INTO dead_letter_queue (
            original_job_id,
            job_type,
            priority,
            payload,
            metadata,
            final_error_type,
            final_error_message,
            final_error_stack,
            final_attempt_count,
            max_retries,
            last_worker_id,
            last_processed_at,
            archived_reason,
            failure_category
        ) VALUES (
            NEW.id,
            NEW.type,
            0,
            NEW.payload,
            COALESCE(NEW.metadata, '{}'::jsonb),
            COALESCE(NEW.last_error, 'UnknownError'),
            NEW.error_message,
            NEW.error_stack,
            NEW.attempts,
            NEW.max_retries,
            NEW.worker_id,
            COALESCE(NEW.finished_at, NEW.started_at, CURRENT_TIMESTAMP),
            CASE
                WHEN NEW.attempts >= NEW.max_retries THEN 'max_retries_exceeded'
                ELSE 'permanent_failure'
            END,
            CASE
                WHEN COALESCE(NEW.error_message, '') ILIKE '%timeout%' THEN 'timeout'
                WHEN COALESCE(NEW.error_message, '') ILIKE '%connection%' THEN 'connection'
                WHEN COALESCE(NEW.error_message, '') ILIKE '%validation%' THEN 'validation'
                WHEN COALESCE(NEW.error_message, '') ILIKE '%permission%' THEN 'permission'
                ELSE 'unknown'
            END
        )
        ON CONFLICT (original_job_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS archive_failed_job_trigger ON jobs;
CREATE TRIGGER archive_failed_job_trigger
AFTER UPDATE ON jobs
FOR EACH ROW EXECUTE FUNCTION archive_to_dead_letter_queue();

CREATE OR REPLACE FUNCTION reprocess_dead_letter_entry(
    dead_letter_id UUID,
    reprocess_reason TEXT DEFAULT 'manual_reprocess'
) RETURNS UUID AS $$
DECLARE
    new_job_id UUID;
    dlq_record dead_letter_queue%ROWTYPE;
BEGIN
    SELECT * INTO dlq_record
    FROM dead_letter_queue
    WHERE id = dead_letter_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Dead letter queue entry not found: %', dead_letter_id;
    END IF;

    INSERT INTO jobs (
        type,
        payload,
        metadata,
        max_retries,
        status,
        error_message,
        error_stack
    ) VALUES (
        dlq_record.job_type,
        dlq_record.payload,
        jsonb_set(
            COALESCE(dlq_record.metadata, '{}'::jsonb),
            '{reprocess_info}',
            jsonb_build_object(
                'original_dead_letter_id', dead_letter_id,
                'reprocess_reason', reprocess_reason,
                'original_failure', dlq_record.final_error_type,
                'previous_attempts', dlq_record.final_attempt_count
            ),
            true
        ),
        dlq_record.max_retries,
        'queued',
        NULL,
        NULL
    ) RETURNING id INTO new_job_id;

    UPDATE dead_letter_queue
    SET resolution_status = 'resolved',
        resolution_notes = CONCAT(
            'Reprocessed as job ', new_job_id, ': ', reprocess_reason
        ),
        resolved_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = dead_letter_id;

    RETURN new_job_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_dead_letter_stats(
    period_start TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP - INTERVAL '7 days',
    period_end TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
) RETURNS TABLE (
    total_entries BIGINT,
    by_failure_category JSONB,
    by_job_type JSONB,
    resolution_summary JSONB,
    avg_time_to_resolution INTERVAL
) AS $$
WITH scoped AS (
    SELECT *
    FROM dead_letter_queue
    WHERE archived_at BETWEEN period_start AND period_end
)
SELECT
    (SELECT COUNT(*) FROM scoped),
    COALESCE(
        (SELECT jsonb_object_agg(category, category_count)
         FROM (
             SELECT COALESCE(failure_category, 'unknown') AS category,
                    COUNT(*) AS category_count
             FROM scoped
             GROUP BY COALESCE(failure_category, 'unknown')
         ) categories),
        '{}'::jsonb
    ),
    COALESCE(
        (SELECT jsonb_object_agg(job_type, type_count)
         FROM (
             SELECT job_type, COUNT(*) AS type_count
             FROM scoped
             GROUP BY job_type
         ) types),
        '{}'::jsonb
    ),
    COALESCE(
        (SELECT jsonb_object_agg(resolution_status, status_count)
         FROM (
             SELECT resolution_status, COUNT(*) AS status_count
             FROM scoped
             GROUP BY resolution_status
         ) resolutions),
        '{}'::jsonb
    ),
    (SELECT AVG(resolved_at - archived_at)
     FROM scoped
     WHERE resolved_at IS NOT NULL);
$$ LANGUAGE SQL STABLE;

CREATE OR REPLACE VIEW recent_dead_letter_entries AS
SELECT
    dlq.*,
    j.created_at AS original_job_created_at,
    j.started_at AS original_job_started_at,
    j.finished_at AS original_job_finished_at,
    AGE(dlq.archived_at, j.created_at) AS time_to_failure
FROM dead_letter_queue dlq
JOIN jobs j ON dlq.original_job_id = j.id
WHERE dlq.archived_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
ORDER BY dlq.archived_at DESC;

CREATE OR REPLACE VIEW unresolved_dead_letter_entries AS
SELECT
    dlq.*,
    j.created_at AS original_job_created_at,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - dlq.archived_at)) / 3600
        AS hours_since_archival
FROM dead_letter_queue dlq
JOIN jobs j ON dlq.original_job_id = j.id
WHERE dlq.resolution_status IN ('pending', 'investigating')
ORDER BY dlq.archived_at ASC;

CREATE OR REPLACE FUNCTION update_dead_letter_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_dead_letter_updated_at ON dead_letter_queue;
CREATE TRIGGER update_dead_letter_updated_at
BEFORE UPDATE ON dead_letter_queue
FOR EACH ROW EXECUTE FUNCTION update_dead_letter_updated_at();

-- RLS is enabled for direct database access. Supabase's service_role policy is
-- created only when that role exists; local PostgreSQL test databases can run
-- the same script without requiring Supabase-specific roles.
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE worker_heartbeat ENABLE ROW LEVEL SECURITY;
ALTER TABLE dead_letter_queue ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        EXECUTE 'DROP POLICY IF EXISTS service_role_full_access ON jobs';
        EXECUTE 'CREATE POLICY service_role_full_access ON jobs FOR ALL TO service_role USING (true) WITH CHECK (true)';
        EXECUTE 'DROP POLICY IF EXISTS service_role_full_access ON worker_heartbeat';
        EXECUTE 'CREATE POLICY service_role_full_access ON worker_heartbeat FOR ALL TO service_role USING (true) WITH CHECK (true)';
        EXECUTE 'DROP POLICY IF EXISTS service_role_full_access ON dead_letter_queue';
        EXECUTE 'CREATE POLICY service_role_full_access ON dead_letter_queue FOR ALL TO service_role USING (true) WITH CHECK (true)';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON jobs, worker_heartbeat, dead_letter_queue TO service_role';
        EXECUTE 'GRANT EXECUTE ON FUNCTION reprocess_dead_letter_entry(UUID, TEXT) TO service_role';
        EXECUTE 'GRANT EXECUTE ON FUNCTION get_dead_letter_stats(TIMESTAMPTZ, TIMESTAMPTZ) TO service_role';
    END IF;
END;
$$;

COMMENT ON TABLE dead_letter_queue IS
    'Stores permanently failed jobs for analysis and controlled reprocessing';
COMMENT ON FUNCTION archive_to_dead_letter_queue() IS
    'Archives a job after it transitions to failed';
COMMENT ON FUNCTION reprocess_dead_letter_entry(UUID, TEXT) IS
    'Creates a queued replacement job from a DLQ entry';
COMMENT ON FUNCTION get_dead_letter_stats(TIMESTAMPTZ, TIMESTAMPTZ) IS
    'Returns DLQ statistics for a time range';

SELECT 'Dead letter queue schema and hardening applied successfully' AS status;
