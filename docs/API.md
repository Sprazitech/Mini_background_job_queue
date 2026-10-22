# API Contract

Production API base URL:

```text
https://mini-background-job-queue.onrender.com
```

Interactive documentation:

```text
https://mini-background-job-queue.onrender.com/docs
```

Protected endpoints require the following header:

```text
X-API-Key: <server-issued API key>
```

The current static frontend asks for this key for controlled MVP testing. Do not
publish the key in frontend source, Vercel environment variables, or logs. A
browser-safe user/session authentication design is still required before public
launch.

## Jobs

### Create a job

```http
POST /jobs
Content-Type: application/json
X-API-Key: <api-key>
```

Supported request types:

```json
{
  "type": "send_email",
  "payload": {
    "to": "recipient@example.com",
    "subject": "Example"
  }
}
```

or:

```json
{
  "type": "generate_report",
  "payload": {
    "report_type": "daily",
    "format": "pdf"
  }
}
```

Successful response: `201 Created` with the job ID, type, status, attempts,
maximum retries, last error, created timestamp, and updated timestamp.

### List jobs

```http
GET /jobs?status=queued&limit=20&offset=0
X-API-Key: <api-key>
```

`status` may be `queued`, `running`, `success`, or `failed`. The response is:

```json
{
  "jobs": [],
  "total": 0
}
```

### Get a job

```http
GET /jobs/{job_id}
X-API-Key: <api-key>
```

## Health and metrics

### Health

```http
GET /health
```

This endpoint does not require the API key and returns database and worker
health. A healthy response has `status: "ok"`, `db: true`, and `worker: true`.

### Metrics

```http
GET /metrics
X-API-Key: <api-key>
```

The response includes:

- `counts_by_status`
- `queue_depth`
- `success_rate`
- `avg_duration_seconds`
- `worker_last_seen`
- `dead_letter_queue`
- `circuit_breakers`
- request and job counters

`queue_depth` is the number of jobs currently in `queued` status.

## Dead-letter queue

All DLQ endpoints require `X-API-Key`.

```http
GET /dead-letter
GET /dead-letter/{entry_id}
GET /dead-letter/stats?days=7
```

Reprocess an entry:

```http
POST /dead-letter/{entry_id}/reprocess
Content-Type: application/json

{
  "reason": "bug_fixed"
}
```

Resolve an entry without reprocessing:

```http
PUT /dead-letter/{entry_id}/resolve
Content-Type: application/json

{
  "resolution_status": "resolved",
  "resolution_notes": "Root cause identified and fixed"
}
```

Valid resolution statuses are `resolved` and `ignored`.

## Error responses

- `401` — missing or invalid API key
- `404` — requested job or DLQ entry does not exist
- `422` — invalid request, UUID, job type, or oversized payload
- `429` — rate limit exceeded
- `500` — unexpected server-side failure
- `503` — health check reports an unhealthy database or worker
