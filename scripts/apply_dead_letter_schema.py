#!/usr/bin/env python
"""Apply and verify the dead-letter queue database extension.

The script intentionally executes the SQL as one PostgreSQL script. Splitting
PL/pgSQL on semicolons breaks function and trigger definitions.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg


SCHEMA_PATH = Path(__file__).with_name("dead_letter_queue.sql")


def postgres_dsn(database_url: str) -> str:
    """Convert SQLAlchemy's async URL to an asyncpg-compatible DSN."""
    if database_url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_url[len("postgresql+asyncpg://") :]
    return database_url


async def apply_dead_letter_schema(database_url: str) -> None:
    """Apply the DLQ schema in one transaction."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    conn = await asyncpg.connect(postgres_dsn(database_url))
    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        async with conn.transaction():
            await conn.execute(schema_sql)
    finally:
        await conn.close()


def _require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


async def verify_dead_letter_schema(database_url: str) -> None:
    """Verify tables, columns, indexes, functions, views, triggers, and RLS."""
    conn = await asyncpg.connect(postgres_dsn(database_url))
    try:
        required_tables = {"jobs", "worker_heartbeat", "dead_letter_queue"}
        table_rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY($1::text[])
            """,
            list(required_tables),
        )
        found_tables = {row["table_name"] for row in table_rows}
        _require(
            found_tables == required_tables,
            f"Missing tables: {sorted(required_tables - found_tables)}",
        )

        required_job_columns = {
            "metadata",
            "error_message",
            "error_stack",
            "worker_id",
        }
        column_rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'jobs'
              AND column_name = ANY($1::text[])
            """,
            list(required_job_columns),
        )
        found_columns = {row["column_name"] for row in column_rows}
        _require(
            found_columns == required_job_columns,
            f"Missing jobs columns: {sorted(required_job_columns - found_columns)}",
        )

        required_indexes = {
            "idx_dead_letter_archived_at",
            "idx_dead_letter_resolution_status",
            "idx_dead_letter_failure_category",
            "idx_dead_letter_original_job_id",
            "idx_dead_letter_created_at",
        }
        index_rows = await conn.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'dead_letter_queue'
              AND indexname = ANY($1::text[])
            """,
            list(required_indexes),
        )
        found_indexes = {row["indexname"] for row in index_rows}
        _require(
            found_indexes == required_indexes,
            f"Missing DLQ indexes: {sorted(required_indexes - found_indexes)}",
        )

        required_functions = {
            "archive_to_dead_letter_queue",
            "reprocess_dead_letter_entry",
            "get_dead_letter_stats",
            "update_dead_letter_updated_at",
        }
        function_rows = await conn.fetch(
            """
            SELECT DISTINCT routine_name
            FROM information_schema.routines
            WHERE routine_schema = 'public'
              AND routine_name = ANY($1::text[])
            """,
            list(required_functions),
        )
        found_functions = {row["routine_name"] for row in function_rows}
        _require(
            found_functions == required_functions,
            f"Missing DLQ functions: {sorted(required_functions - found_functions)}",
        )

        required_views = {
            "recent_dead_letter_entries",
            "unresolved_dead_letter_entries",
        }
        view_rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
              AND table_name = ANY($1::text[])
            """,
            list(required_views),
        )
        found_views = {row["table_name"] for row in view_rows}
        _require(
            found_views == required_views,
            f"Missing DLQ views: {sorted(required_views - found_views)}",
        )

        trigger_rows = await conn.fetch(
            """
            SELECT tgname
            FROM pg_trigger trigger_info
            JOIN pg_class table_info ON table_info.oid = trigger_info.tgrelid
            JOIN pg_namespace namespace_info ON namespace_info.oid = table_info.relnamespace
            WHERE namespace_info.nspname = 'public'
              AND table_info.relname = 'jobs'
              AND NOT trigger_info.tgisinternal
              AND tgname = 'archive_failed_job_trigger'
            """
        )
        _require(bool(trigger_rows), "DLQ archive trigger not found")

        rls_rows = await conn.fetch(
            """
            SELECT relname, relrowsecurity
            FROM pg_class table_info
            JOIN pg_namespace namespace_info ON namespace_info.oid = table_info.relnamespace
            WHERE namespace_info.nspname = 'public'
              AND relname = ANY($1::text[])
            """,
            ["jobs", "worker_heartbeat", "dead_letter_queue"],
        )
        rls = {row["relname"]: row["relrowsecurity"] for row in rls_rows}
        _require(
            all(rls.get(table_name) for table_name in ("jobs", "worker_heartbeat", "dead_letter_queue")),
            "RLS is not enabled on every queue table",
        )
    finally:
        await conn.close()


async def main(verify_only: bool) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    if not verify_only:
        print("Applying dead-letter queue schema...")
        await apply_dead_letter_schema(database_url)
        print("Dead-letter queue schema applied")

    print("Verifying dead-letter queue schema...")
    await verify_dead_letter_schema(database_url)
    print("Dead-letter queue schema verification passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the existing schema without applying SQL",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(verify_only=args.verify))
    except Exception as exc:
        print(f"Dead-letter queue setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
