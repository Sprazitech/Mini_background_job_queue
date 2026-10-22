-- Dead Letter Queue Schema Extension
-- Adds dead_letter_queue table and related functions for permanently failed jobs

-- Dead Letter Queue Table
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Original job data
    original_job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    job_type VARCHAR(100) NOT NULL,
    priority INTEGER NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Failure details
    final_error_type VARCHAR(100) NOT NULL,
    final_error_message TEXT,
    final_error_stack TEXT,
    final_attempt_count INTEGER NOT NULL,
    max_retries INTEGER NOT NULL,
    
    -- Execution context
    last_worker_id VARCHAR(100),
    last_processed_at TIMESTAMP WITH TIME ZONE,
    
    -- Archival metadata
    archived_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_reason VARCHAR(100) NOT NULL CHECK (
        archived_reason IN ('max_retries_exceeded', 'permanent_failure', 'manual_archival', 'system_cleanup')
    ),
    
    -- Analysis and resolution
    failure_category VARCHAR(100),
    suggested_fix TEXT,
    resolution_status VARCHAR(50) DEFAULT 'pending' CHECK (
        resolution_status IN ('pending', 'investigating', 'resolved', 'ignored')
    ),
    resolution_notes TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(100),
    
    -- Indexes for performance
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Dead Letter Queue
CREATE INDEX idx_dead_letter_archived_at ON dead_letter_queue(archived_at);
CREATE INDEX idx_dead_letter_resolution_status ON dead_letter_queue(resolution_status);
CREATE INDEX idx_dead_letter_failure_category ON dead_letter_queue(failure_category);
CREATE INDEX idx_dead_letter_original_job_id ON dead_letter_queue(original_job_id);
CREATE INDEX idx_dead_letter_created_at ON dead_letter_queue(created_at);

-- Function to archive failed jobs to dead letter queue
CREATE OR REPLACE FUNCTION archive_to_dead_letter_queue()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'failed' AND OLD.status != 'failed' THEN
        INSERT INTO dead_letter_queue (
            original_job_id, job_type, priority, payload, metadata,
            final_error_type, final_error_message, final_error_stack,
            final_attempt_count, max_retries, last_worker_id, last_processed_at,
            archived_reason, failure_category
        ) VALUES (
            NEW.id, NEW.job_type, NEW.priority, NEW.payload, NEW.metadata,
            COALESCE(NEW.last_error, 'UnknownError'),
            NEW.error_message,
            NEW.error_stack,
            NEW.attempts,
            NEW.max_retries,
            NEW.worker_id,
            NEW.started_at,
            CASE 
                WHEN NEW.attempts >= NEW.max_retries THEN 'max_retries_exceeded'
                ELSE 'permanent_failure'
            END,
            CASE 
                WHEN NEW.last_error LIKE '%Timeout%' THEN 'timeout'
                WHEN NEW.last_error LIKE '%Connection%' THEN 'connection'
                WHEN NEW.last_error LIKE '%Validation%' THEN 'validation'
                WHEN NEW.last_error LIKE '%Permission%' THEN 'permission'
                ELSE 'unknown'
            END
        );
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically archive failed jobs
DROP TRIGGER IF EXISTS archive_failed_job_trigger ON jobs;
CREATE TRIGGER archive_failed_job_trigger AFTER UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION archive_to_dead_letter_queue();

-- Function to reprocess a dead letter queue entry
CREATE OR REPLACE FUNCTION reprocess_dead_letter_entry(
    dead_letter_id UUID,
    reprocess_reason TEXT DEFAULT 'manual_reprocess'
) RETURNS UUID AS $$
DECLARE
    new_job_id UUID;
    dlq_record RECORD;
BEGIN
    -- Get the dead letter queue record
    SELECT * INTO dlq_record FROM dead_letter_queue WHERE id = dead_letter_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Dead letter queue entry not found: %', dead_letter_id;
    END IF;
    
    -- Create a new job from the archived data
    INSERT INTO jobs (
        job_type, priority, payload, metadata,
        max_retries, status, error_message, error_stack
    ) VALUES (
        dlq_record.job_type,
        dlq_record.priority,
        dlq_record.payload,
        jsonb_set(
            dlq_record.metadata,
            '{reprocess_info}',
            jsonb_build_object(
                'original_dead_letter_id', dead_letter_id,
                'reprocess_reason', reprocess_reason,
                'original_failure', dlq_record.final_error_type,
                'previous_attempts', dlq_record.final_attempt_count
            )
        ),
        dlq_record.max_retries,
        'queued',
        dlq_record.final_error_message,
        dlq_record.final_error_stack
    ) RETURNING id INTO new_job_id;
    
    -- Update the dead letter queue entry
    UPDATE dead_letter_queue
    SET 
        resolution_status = 'resolved',
        resolution_notes = CONCAT('Reprocessed as job ', new_job_id, ': ', reprocess_reason),
        resolved_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = dead_letter_id;
    
    RETURN new_job_id;
END;
$$ language 'plpgsql';

-- Function to get dead letter queue statistics
CREATE OR REPLACE FUNCTION get_dead_letter_stats(
    period_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '7 days',
    period_end TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) RETURNS TABLE (
    total_entries BIGINT,
    by_failure_category JSONB,
    by_job_type JSONB,
    resolution_summary JSONB,
    avg_time_to_resolution INTERVAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT as total_entries,
        jsonb_object_agg(
            COALESCE(failure_category, 'unknown'),
            category_count
        ) as by_failure_category,
        jsonb_object_agg(
            job_type,
            type_count
        ) as by_job_type,
        jsonb_object_agg(
            COALESCE(resolution_status, 'pending'),
            status_count
        ) as resolution_summary,
        AVG(resolved_at - archived_at) FILTER (WHERE resolved_at IS NOT NULL) as avg_time_to_resolution
    FROM (
        SELECT
            failure_category,
            job_type,
            resolution_status,
            COUNT(*) as total_count,
            COUNT(*) FILTER (WHERE failure_category IS NOT NULL) as category_count,
            COUNT(*) FILTER (WHERE job_type IS NOT NULL) as type_count,
            COUNT(*) FILTER (WHERE resolution_status IS NOT NULL) as status_count
        FROM dead_letter_queue
        WHERE archived_at BETWEEN period_start AND period_end
        GROUP BY GROUPING SETS (
            (failure_category),
            (job_type),
            (resolution_status)
        )
    ) stats;
END;
$$ language 'plpgsql';

-- View for recent dead letter queue entries
CREATE OR REPLACE VIEW recent_dead_letter_entries AS
SELECT
    dlq.*,
    j.created_at as original_job_created_at,
    j.started_at as original_job_started_at,
    AGE(dlq.archived_at, j.created_at) as time_to_failure
FROM dead_letter_queue dlq
JOIN jobs j ON dlq.original_job_id = j.id
WHERE dlq.archived_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
ORDER BY dlq.archived_at DESC;

-- View for unresolved dead letter entries
CREATE OR REPLACE VIEW unresolved_dead_letter_entries AS
SELECT
    dlq.*,
    j.created_at as original_job_created_at,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - dlq.archived_at)) / 3600 as hours_since_archival
FROM dead_letter_queue dlq
JOIN jobs j ON dlq.original_job_id = j.id
WHERE dlq.resolution_status IN ('pending', 'investigating')
ORDER BY dlq.archived_at ASC;

-- Update trigger for dead_letter_queue updated_at
CREATE OR REPLACE FUNCTION update_dead_letter_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_dead_letter_updated_at BEFORE UPDATE ON dead_letter_queue
    FOR EACH ROW EXECUTE FUNCTION update_dead_letter_updated_at();

-- Comments for documentation
COMMENT ON TABLE dead_letter_queue IS 'Stores permanently failed jobs for analysis and potential reprocessing';
COMMENT ON COLUMN dead_letter_queue.failure_category IS 'Categorized failure reason for analysis';
COMMENT ON COLUMN dead_letter_queue.resolution_status IS 'Tracking state of investigation/resolution';
COMMENT ON COLUMN dead_letter_queue.suggested_fix IS 'Suggested fix or workaround for the failure';

COMMENT ON FUNCTION archive_to_dead_letter_queue() IS 'Automatically archives failed jobs to dead letter queue';
COMMENT ON FUNCTION reprocess_dead_letter_entry(UUID, TEXT) IS 'Reprocesses a dead letter queue entry as a new job';
COMMENT ON FUNCTION get_dead_letter_stats(TIMESTAMP, TIMESTAMP) IS 'Returns statistics about dead letter queue entries';

-- Apply the schema changes
SELECT 'Dead letter queue schema created successfully' as status;