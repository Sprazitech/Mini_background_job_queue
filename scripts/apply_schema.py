import asyncio
import os
import sys
from pathlib import Path

import asyncpg


DEFAULT_LOCAL_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"


def resolve_database_url() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("LOCAL_DATABASE_URL")
        or DEFAULT_LOCAL_DATABASE_URL
    )


async def main() -> None:
    database_url = resolve_database_url()
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
        print(
            "Could not connect to the database.\n"
            f"Tried: {dsn}\n"
            "Check your DATABASE_URL / LOCAL_DATABASE_URL and confirm the host is reachable.\n"
            "For local testing, start Postgres and use: "
            f"{DEFAULT_LOCAL_DATABASE_URL}\n"
            f"Original error: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    try:
        await conn.execute(schema_sql)
    finally:
        await conn.close()

    print("Schema applied")


if __name__ == "__main__":
    asyncio.run(main())
