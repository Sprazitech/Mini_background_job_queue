import asyncio
import logging
from datetime import datetime, timezone
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

# Circuit breaker tracking
_circuit_breakers = {}
CIRCUIT_BREAKER_THRESHOLD = 5  # Number of consecutive failures before opening
CIRCUIT_BREAKER_RESET_TIMEOUT = 300  # 5 minutes in seconds


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
        error_type = type(error).__name__
        logger.error(
            "job_failed",
            extra={
                "job_id": str(job_id),
                "attempt": attempts,
                "error_type": error_type,
                "job_type": job["type"],
            },
        )
        
        # Update circuit breaker for this job type
        job_type = job["type"]
        if job_type not in _circuit_breakers:
            _circuit_breakers[job_type] = {"failures": 0, "last_failure": None}
        
        cb = _circuit_breakers[job_type]
        cb["failures"] += 1
        cb["last_failure"] = datetime.now(timezone.utc)
        
        # Check if circuit breaker should open
        if cb["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(
                "circuit_breaker_opened",
                extra={
                    "job_type": job_type,
                    "consecutive_failures": cb["failures"],
                    "threshold": CIRCUIT_BREAKER_THRESHOLD,
                },
            )
        
        async with session_factory() as session:
            if attempts >= job["max_retries"]:
                # Job has exhausted all retries - mark as failed
                # The trigger will automatically archive to dead letter queue
                await session.execute(
                    text(
                        """
                        UPDATE jobs
                        SET status = 'failed', last_error = :last_error,
                            error_message = :error_message, finished_at = now()
                        WHERE id = :job_id
                        """
                    ),
                    {
                        "job_id": job_id,
                        "last_error": error_type,
                        "error_message": str(error)[:500],  # Truncate long error messages
                    },
                )
                increment_jobs_failed_total()
                
                # Log dead letter queue archival
                logger.warning(
                    "job_archived_to_dead_letter",
                    extra={
                        "job_id": str(job_id),
                        "job_type": job_type,
                        "attempts": attempts,
                        "max_retries": job["max_retries"],
                        "error_type": error_type,
                    },
                )
            else:
                # Calculate next attempt with circuit breaker consideration
                base_delay = calculate_next_attempt(attempts)
                
                # If circuit breaker is open, add additional delay
                if cb["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
                    additional_delay = CIRCUIT_BREAKER_RESET_TIMEOUT
                    logger.info(
                        "circuit_breaker_delay_applied",
                        extra={
                            "job_id": str(job_id),
                            "job_type": job_type,
                            "additional_delay_seconds": additional_delay,
                        },
                    )
                else:
                    additional_delay = 0
                
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
                        "next_attempt_at": base_delay,
                    },
                )
            await session.execute(UPDATE_HEARTBEAT)
            await session.commit()
        
        # Reset circuit breaker if enough time has passed
        if (cb["failures"] >= CIRCUIT_BREAKER_THRESHOLD and 
            cb["last_failure"] and 
            (datetime.now(timezone.utc) - cb["last_failure"]).seconds >= CIRCUIT_BREAKER_RESET_TIMEOUT):
            logger.info(
                "circuit_breaker_reset",
                extra={"job_type": job_type},
            )
            cb["failures"] = 0
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


def get_circuit_breaker_status() -> dict:
    """Get current circuit breaker status for monitoring."""
    status = {}
    for job_type, cb in _circuit_breakers.items():
        is_open = cb["failures"] >= CIRCUIT_BREAKER_THRESHOLD
        status[job_type] = {
            "failures": cb["failures"],
            "threshold": CIRCUIT_BREAKER_THRESHOLD,
            "is_open": is_open,
            "last_failure": cb["last_failure"].isoformat() if cb["last_failure"] else None,
            "time_since_last_failure": (
                (datetime.now(timezone.utc) - cb["last_failure"]).seconds 
                if cb["last_failure"] else None
            ),
        }
    return status


def reset_circuit_breaker(job_type: str) -> bool:
    """Manually reset circuit breaker for a job type."""
    if job_type in _circuit_breakers:
        _circuit_breakers[job_type]["failures"] = 0
        logger.info(
            "circuit_breaker_manually_reset",
            extra={"job_type": job_type},
        )
        return True
    return False


def get_worker_stats() -> dict:
    """Get worker statistics including circuit breaker status."""
    return {
        "circuit_breakers": get_circuit_breaker_status(),
        "active_handlers": list(HANDLERS.keys()),
        "circuit_breaker_threshold": CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_reset_timeout": CIRCUIT_BREAKER_RESET_TIMEOUT,
    }