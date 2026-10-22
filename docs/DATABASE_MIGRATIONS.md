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
