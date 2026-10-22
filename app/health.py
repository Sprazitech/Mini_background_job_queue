import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Job, WorkerHeartbeat
from app.security import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

requests_total = 0
jobs_submitted_total = 0
jobs_failed_total = 0


def increment_jobs_failed_total() -> None:
    global jobs_failed_total
    jobs_failed_total += 1


@event.listens_for(Session, "after_flush")
def _track_submitted_jobs(session: Session, _: object) -> None:
    new_jobs = sum(isinstance(item, Job) for item in session.new)
    if new_jobs:
        session.info["jobs_submitted_pending"] = (
            session.info.get("jobs_submitted_pending", 0) + new_jobs
        )


@event.listens_for(Session, "after_commit")
def _count_submitted_jobs(session: Session) -> None:
    global jobs_submitted_total
    jobs_submitted_total += session.info.pop("jobs_submitted_pending", 0)


@event.listens_for(Session, "after_rollback")
def _discard_uncommitted_jobs(session: Session) -> None:
    session.info.pop("jobs_submitted_pending", None)


async def _count_health_request() -> None:
    global requests_total
    requests_total += 1


@router.get("/health", dependencies=[Depends(_count_health_request)])
async def health(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool | str]:
    database_ok = False
    worker_ok = False
    try:
        await session.execute(text("SELECT 1"))
        database_ok = True
        last_seen = await session.scalar(
            select(WorkerHeartbeat.last_seen).where(WorkerHeartbeat.id == 1)
        )
        worker_ok = bool(
            last_seen
            and last_seen >= datetime.now(timezone.utc) - timedelta(seconds=60)
        )
    except SQLAlchemyError:
        logger.exception("health_check_failed")

    if not database_ok or not worker_ok:
        response.status_code = 503
    return {
        "status": "ok" if database_ok and worker_ok else "unhealthy",
        "db": database_ok,
        "worker": worker_ok,
    }


@router.get(
    "/metrics",
    dependencies=[Depends(_count_health_request), Depends(verify_api_key)],
)
async def metrics(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    # Job statistics
    statuses = await session.execute(
        select(Job.status, func.count()).group_by(Job.status)
    )
    counts = {status: count for status, count in statuses}
    
    # Worker heartbeat
    last_seen = await session.scalar(
        select(WorkerHeartbeat.last_seen).where(WorkerHeartbeat.id == 1)
    )
    
    # Average duration
    average_duration = await session.scalar(
        select(
            func.avg(
                func.extract("epoch", Job.finished_at - Job.started_at)
            )
        ).where(Job.status == "success")
    )
    
    # Dead letter queue statistics (if table exists)
    dead_letter_stats = {}
    try:
        # Check if dead_letter_queue table exists
        table_exists = await session.scalar(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'dead_letter_queue'
                )
            """)
        )
        
        if table_exists:
            # Get dead letter queue counts
            dlq_counts = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE resolution_status = 'pending') as pending,
                        COUNT(*) FILTER (WHERE resolution_status = 'resolved') as resolved,
                        COUNT(*) FILTER (WHERE resolution_status = 'investigating') as investigating
                    FROM dead_letter_queue
                """)
            )
            dlq_row = dlq_counts.mappings().first()
            
            # Get failure categories
            failure_categories = await session.execute(
                text("""
                    SELECT 
                        COALESCE(failure_category, 'unknown') as category,
                        COUNT(*) as count
                    FROM dead_letter_queue
                    GROUP BY failure_category
                    ORDER BY count DESC
                """)
            )
            
            dead_letter_stats = {
                "total": dlq_row["total"] if dlq_row else 0,
                "pending": dlq_row["pending"] if dlq_row else 0,
                "resolved": dlq_row["resolved"] if dlq_row else 0,
                "investigating": dlq_row["investigating"] if dlq_row else 0,
                "failure_categories": {
                    row["category"]: row["count"] 
                    for row in failure_categories.mappings()
                },
            }
    except Exception as e:
        logger.warning(f"Could not fetch dead letter queue stats: {e}")
        dead_letter_stats = {"error": "Stats unavailable"}
    
    # Calculate success rate
    successful = counts.get("success", 0)
    failed = counts.get("failed", 0)
    completed = successful + failed
    
    # Get circuit breaker status
    from app.worker.loop import get_circuit_breaker_status
    circuit_breakers = get_circuit_breaker_status()
    
    return {
        "counts_by_status": counts,
        "queue_depth": counts.get("queued", 0),
        "worker_last_seen": last_seen.isoformat() if last_seen else None,
        "avg_duration_seconds": float(average_duration or 0),
        "success_rate": successful / completed if completed else 0,
        "dead_letter_queue": dead_letter_stats,
        "circuit_breakers": circuit_breakers,
        "requests_total": requests_total,
        "jobs_submitted_total": jobs_submitted_total,
        "jobs_failed_total": jobs_failed_total,
    }
