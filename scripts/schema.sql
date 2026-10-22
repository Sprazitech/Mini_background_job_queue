CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL CHECK (type IN ('send_email','generate_report')),
    payload JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','success','failed')),
    attempts INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    error_message TEXT,
    error_stack TEXT,
    worker_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS worker_heartbeat (
    id INT PRIMARY KEY DEFAULT 1,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_next_attempt
    ON jobs(status, next_attempt_at)
    WHERE status = 'queued';
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE worker_heartbeat ENABLE ROW LEVEL SECURITY;
INSERT INTO worker_heartbeat (id, last_seen) VALUES (1, now())
ON CONFLICT (id) DO NOTHING;
