# Database models and migrations

The SQLAlchemy models in `app/models.py` mirror `scripts/schema.sql`. Alembic
uses the asyncpg driver and reads `DATABASE_URL` from the environment; it does
not load `.env` automatically.

## Install dependencies

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Load the private connection settings in the same shell before running Alembic:

```bash
set -a
source .env
set +a
```

## Existing Supabase database

The initial schema has already been applied to the project. After confirming
that its tables, columns, constraints, index, and RLS settings match
`scripts/schema.sql`, register the existing schema as the initial Alembic
revision:

```bash
alembic stamp head
alembic current
```

`stamp` records the revision without executing the migration. Do **not** run
`alembic upgrade head` on this already-created database before stamping it:
the initial migration creates tables and would fail on existing tables.

## New empty database

For a new database with no queue tables, run:

```bash
alembic upgrade head
```

To add future schema changes, create a revision, inspect its generated file,
then apply it with `alembic upgrade head`. Review generated migrations before
applying them to Supabase.

## Worker and dead-letter queue columns

Revision `20261022_02_add_worker_dlq_columns.py` adds the job metadata and error
context columns required by the worker and dead-letter queue trigger:

- `metadata`
- `error_message`
- `error_stack`
- `worker_id`

For the existing Supabase database, apply the revision after confirming the
Alembic baseline, or run the idempotent DLQ extension script:

```bash
python scripts/apply_dead_letter_schema.py
python scripts/apply_dead_letter_schema.py --verify
```

The DLQ script applies the trigger, functions, views, indexes, and RLS checks in
one PostgreSQL transaction. It must use the intended database connection and
must not be run with local placeholder credentials against production.
