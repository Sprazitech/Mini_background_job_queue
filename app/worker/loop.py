import asyncio
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import SessionLocal
from app.health import increment_jobs_failed_total
from app.worker.handlers import HANDLERS
from app.worker.retry import calculate_next_attempt

logger = logging.getLogger(__name__)

CLAIM_JOB = text(
    """
    UPDATE jobs
    SET status = 'running', started_at = now(), attempts = attempts + 1
    WHERE id = (
        SELECT id
        FROM jobs
        WHERE status = 'queued' AND next_attempt_at <= now()
        ORDER BY created_at
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *
    """
)
UPDATE_HEARTBEAT = text(
    "UPDATE worker_heartbeat SET last_seen = now() WHERE id = 1"
)


async def run_worker_cycle(
    session_factory: async_sessionmaker = SessionLocal,
) -> bool:
    async with session_factory() as session:
        result = await session.execute(CLAIM_JOB)
        job = result.mappings().one_or_none()
        await session.commit()

    if job is None:
        async with session_factory() as session:
            await session.execute(UPDATE_HEARTBEAT)
            await session.commit()
        return False

    job_id = job["id"]
    attempts = job["attempts"]
    try:
        handler = HANDLERS[job["type"]]
        await asyncio.wait_for(handler(job["payload"]), timeout=30)
    except asyncio.CancelledError:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE jobs
                    SET status = 'queued', next_attempt_at = now()
                    WHERE id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
            await session.commit()
        raise
    except Exception as error:
        logger.error(
            "job_failed",
            extra={
                "job_id": str(job_id),
                "attempt": attempts,
                "error_type": type(error).__name__,
            },
        )
        async with session_factory() as session:
            if attempts >= job["max_retries"]:
                await session.execute(
                    text(
                        """
                        UPDATE jobs
                        SET status = 'failed', last_error = :last_error,
                            finished_at = now()
                        WHERE id = :job_id
                        """
                    ),
                    {"job_id": job_id, "last_error": type(error).__name__},
                )
                increment_jobs_failed_total()
            else:
                await session.execute(
                    text(
                        """
                        UPDATE jobs
                        SET status = 'queued', next_attempt_at = :next_attempt_at
                        WHERE id = :job_id
                        """
                    ),
                    {
                        "job_id": job_id,
                        "next_attempt_at": calculate_next_attempt(attempts),
                    },
                )
            await session.execute(UPDATE_HEARTBEAT)
            await session.commit()
    else:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE jobs
                    SET status = 'success', finished_at = now()
                    WHERE id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
            await session.execute(UPDATE_HEARTBEAT)
            await session.commit()
    return True


async def worker_loop() -> None:
    while True:
        claimed = await run_worker_cycle()
        if not claimed:
            await asyncio.sleep(2)


async def start_worker() -> asyncio.Task[None]:
    return asyncio.create_task(worker_loop(), name="job-worker")


async def stop_worker(task: asyncio.Task[Any]) -> None:
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=10)
    except asyncio.CancelledError:
        pass
