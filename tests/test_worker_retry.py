import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base
from app.worker.loop import run_worker_cycle

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to run worker tests against a dedicated PostgreSQL database.",
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield factory

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_job_is_retried_then_marked_failed(session_factory):
    async with session_factory() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO jobs (type, payload, max_retries)
                VALUES ('send_email', '{"force_fail": true}'::jsonb, 2)
                RETURNING id
                """
            )
        )
        job_id = result.scalar_one()
        await session.commit()

    await run_worker_cycle(session_factory)

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT status, attempts FROM jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
        assert result.one() == ("queued", 1)
        await session.execute(
            text(
                "UPDATE jobs SET next_attempt_at = :now WHERE id = :job_id"
            ),
            {"job_id": job_id, "now": datetime.now(timezone.utc)},
        )
        await session.commit()

    await run_worker_cycle(session_factory)

    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT status, attempts, last_error FROM jobs WHERE id = :job_id"
            ),
            {"job_id": job_id},
        )
        assert result.one() == ("failed", 2, "ValueError")
