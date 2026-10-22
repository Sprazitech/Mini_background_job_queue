# Database Operations Runbook

This runbook covers the M4 operational checks that cannot be proved from source
code alone. Production checks must be performed by M4/M5 in the Supabase and
Render dashboards without placing credentials in Git or chat.

## 1. Apply and verify the dead-letter queue schema

Use the production `DATABASE_URL` only in a secure shell or the Render shell:

```bash
python scripts/apply_dead_letter_schema.py
```

To verify without applying changes:

```bash
python scripts/apply_dead_letter_schema.py --verify
```

The script verifies:

- `jobs`, `worker_heartbeat`, and `dead_letter_queue` tables
- Worker/DLQ job context columns
- DLQ indexes
- Archive, reprocess, statistics, and timestamp functions
- Recent and unresolved DLQ views
- The failed-job archive trigger
- RLS enabled on all queue tables

Do not run the script with the local placeholder `.env` values against a
production database. Never print the connection string or service-role key.

## 2. Dedicated test database

CI provides an isolated PostgreSQL service for each workflow run:

```text
postgresql+asyncpg://test:test@localhost:5432/jobqueue_test
```

The CI workflow exposes this as `TEST_DATABASE_URL`. A separately provisioned
shared test database may be used for manual integration testing, but it must not
be the production Supabase database.

Before running tests manually, set `TEST_DATABASE_URL` to the dedicated test
connection string. The API and worker fixtures create and remove their test
schema; do not point them at production.

## 3. RLS and least privilege

M4/M5 must verify these settings in Supabase:

```sql
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN ('jobs', 'worker_heartbeat', 'dead_letter_queue');

SELECT schemaname, tablename, policyname, roles, cmd
FROM pg_policies
WHERE tablename IN ('jobs', 'worker_heartbeat', 'dead_letter_queue');
```

The schema enables RLS and creates a conditional `service_role` policy when
that Supabase role exists. Anonymous and authenticated browser roles should not
receive direct table access. The application should use a server-side database
role or the approved Supabase service role; neither database credentials nor a
service-role key belongs in Vercel frontend settings.

For a stronger least-privilege deployment, M4/M5 should provision a dedicated
backend database role with only the required table and function privileges.
Record the role and grant review in the team’s secure operations record; do not
commit its password.

## 4. Backup and recovery confirmation

M5 must confirm in Supabase Dashboard:

- Automated backups are enabled for the project.
- The retention period is recorded.
- Point-in-time recovery availability is recorded if included in the plan.
- A recent backup exists.
- A restore procedure has an owner and has been tested in a non-production
  database.
- The restore procedure includes the main schema and DLQ schema.
- API and worker secrets can be reconfigured after a restore.

A backup setting cannot be confirmed from this repository. The confirmation
should include the date, retention setting, test-restore result, and owner,
but must not include credentials.

## 5. Troubleshooting

- **Missing `psycopg2`:** Use a `postgresql+asyncpg://` URL. Do not add a
  synchronous driver to the async application.
- **Missing DLQ columns:** Run the DLQ schema script or Alembic migration
  `20261022_02` against the intended database.
- **No DLQ entry after failure:** Verify the job transitioned from a non-failed
  status to `failed`, then inspect `archive_failed_job_trigger`.
- **Health reports `db=false`:** Check the Render `DATABASE_URL`, pooler host,
  port, password encoding, and database reachability.
- **Health reports `worker=false`:** Confirm `WORKER_ENABLED=true` and inspect
  the worker heartbeat update logs.
- **RLS access denied:** Review the active role and `pg_policies`; do not solve
  this by exposing service credentials to the frontend.
