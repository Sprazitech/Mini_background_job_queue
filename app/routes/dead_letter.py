"""
Dead Letter Queue Management API endpoints.
Provides endpoints to view, analyze, and manage dead letter queue entries.
"""

import logging
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select

from app.database import get_session
from app.security import verify_api_key
from app.schemas import DeadLetterEntry, DeadLetterStats, ReprocessResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dead-letter-queue"], dependencies=[Depends(verify_api_key)])


@router.get("/dead-letter", response_model=List[DeadLetterEntry])
async def list_dead_letter_entries(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    resolution_status: Optional[str] = Query(None),
    failure_category: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
) -> List[DeadLetterEntry]:
    """
    List dead letter queue entries with optional filtering.
    
    Returns paginated list of entries that can be filtered by:
    - resolution_status: pending, investigating, resolved, ignored
    - failure_category: timeout, connection, validation, permission, unknown
    - job_type: send_email, generate_report, etc.
    """
    try:
        # Build query
        query = text("""
            SELECT 
                dlq.*,
                j.created_at as original_job_created_at,
                j.started_at as original_job_started_at,
                EXTRACT(EPOCH FROM (dlq.archived_at - j.created_at)) as time_to_failure_seconds
            FROM dead_letter_queue dlq
            JOIN jobs j ON dlq.original_job_id = j.id
            WHERE 1=1
        """)
        
        params = {}
        
        # Apply filters
        if resolution_status:
            query = text(str(query) + " AND dlq.resolution_status = :resolution_status")
            params["resolution_status"] = resolution_status
        
        if failure_category:
            query = text(str(query) + " AND dlq.failure_category = :failure_category")
            params["failure_category"] = failure_category
        
        if job_type:
            query = text(str(query) + " AND dlq.job_type = :job_type")
            params["job_type"] = job_type
        
        # Add ordering and pagination
        query = text(str(query) + """
            ORDER BY dlq.archived_at DESC
            LIMIT :limit OFFSET :offset
        """)
        params["limit"] = limit
        params["offset"] = offset
        
        # Execute query
        result = await session.execute(query, params)
        rows = result.mappings().all()
        
        return [
            DeadLetterEntry(
                id=row["id"],
                original_job_id=row["original_job_id"],
                job_type=row["job_type"],
                priority=row["priority"],
                payload=row["payload"],
                metadata=row["metadata"],
                final_error_type=row["final_error_type"],
                final_error_message=row["final_error_message"],
                final_attempt_count=row["final_attempt_count"],
                max_retries=row["max_retries"],
                archived_at=row["archived_at"],
                archived_reason=row["archived_reason"],
                failure_category=row["failure_category"],
                resolution_status=row["resolution_status"],
                resolution_notes=row["resolution_notes"],
                suggested_fix=row["suggested_fix"],
                original_job_created_at=row["original_job_created_at"],
                time_to_failure_seconds=row["time_to_failure_seconds"],
            )
            for row in rows
        ]
        
    except Exception as e:
        logger.error(f"Error listing dead letter entries: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dead-letter/{entry_id}", response_model=DeadLetterEntry)
async def get_dead_letter_entry(
    entry_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> DeadLetterEntry:
    """
    Get a specific dead letter queue entry by ID.
    
    Returns detailed information about a single dead letter entry.
    """
    try:
        result = await session.execute(
            text("""
                SELECT 
                    dlq.*,
                    j.created_at as original_job_created_at,
                    j.started_at as original_job_started_at,
                    j.finished_at as original_job_finished_at,
                    EXTRACT(EPOCH FROM (dlq.archived_at - j.created_at)) as time_to_failure_seconds
                FROM dead_letter_queue dlq
                JOIN jobs j ON dlq.original_job_id = j.id
                WHERE dlq.id = :entry_id
            """),
            {"entry_id": str(entry_id)},
        )
        
        row = result.mappings().first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Dead letter entry not found")
        
        return DeadLetterEntry(
            id=row["id"],
            original_job_id=row["original_job_id"],
            job_type=row["job_type"],
            priority=row["priority"],
            payload=row["payload"],
            metadata=row["metadata"],
            final_error_type=row["final_error_type"],
            final_error_message=row["final_error_message"],
            final_error_stack=row["final_error_stack"],
            final_attempt_count=row["final_attempt_count"],
            max_retries=row["max_retries"],
            archived_at=row["archived_at"],
            archived_reason=row["archived_reason"],
            failure_category=row["failure_category"],
            resolution_status=row["resolution_status"],
            resolution_notes=row["resolution_notes"],
            suggested_fix=row["suggested_fix"],
            original_job_created_at=row["original_job_created_at"],
            original_job_started_at=row["original_job_started_at"],
            original_job_finished_at=row["original_job_finished_at"],
            time_to_failure_seconds=row["time_to_failure_seconds"],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dead letter entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/dead-letter/{entry_id}/reprocess", response_model=ReprocessResponse)
async def reprocess_dead_letter_entry(
    entry_id: UUID,
    reason: Optional[str] = "manual_reprocess",
    session: AsyncSession = Depends(get_session),
) -> ReprocessResponse:
    """
    Reprocess a dead letter queue entry as a new job.
    
    Creates a new job from the archived data and marks the dead letter
    entry as resolved.
    
    Parameters:
    - reason: Reason for reprocessing (e.g., "bug_fixed", "manual_intervention")
    """
    try:
        # Call the database function to reprocess
        result = await session.execute(
            text("SELECT reprocess_dead_letter_entry(:entry_id, :reason) as new_job_id"),
            {"entry_id": str(entry_id), "reason": reason},
        )
        
        new_job_id = result.scalar()
        
        if not new_job_id:
            raise HTTPException(status_code=404, detail="Failed to reprocess entry")
        
        await session.commit()
        
        logger.info(
            "dead_letter_reprocessed",
            extra={
                "dead_letter_id": str(entry_id),
                "new_job_id": str(new_job_id),
                "reason": reason,
            },
        )
        
        return ReprocessResponse(
            success=True,
            message=f"Entry reprocessed as new job {new_job_id}",
            new_job_id=new_job_id,
            dead_letter_id=entry_id,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Error reprocessing dead letter entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/dead-letter/{entry_id}/resolve")
async def resolve_dead_letter_entry(
    entry_id: UUID,
    resolution_notes: str,
    resolution_status: str = "resolved",
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """
    Manually resolve a dead letter queue entry without reprocessing.
    
    Use this when the failure has been investigated and no reprocessing is needed.
    """
    if resolution_status not in ["resolved", "ignored"]:
        raise HTTPException(
            status_code=400, 
            detail="resolution_status must be 'resolved' or 'ignored'"
        )
    
    try:
        result = await session.execute(
            text("""
                UPDATE dead_letter_queue
                SET 
                    resolution_status = :resolution_status,
                    resolution_notes = :resolution_notes,
                    resolved_at = NOW(),
                    updated_at = NOW()
                WHERE id = :entry_id
                RETURNING id
            """),
            {
                "entry_id": str(entry_id),
                "resolution_status": resolution_status,
                "resolution_notes": resolution_notes,
            },
        )
        
        if not result.scalar():
            raise HTTPException(status_code=404, detail="Dead letter entry not found")
        
        await session.commit()
        
        logger.info(
            "dead_letter_resolved",
            extra={
                "dead_letter_id": str(entry_id),
                "resolution_status": resolution_status,
                "resolution_notes": resolution_notes,
            },
        )
        
        return {
            "success": True,
            "message": f"Entry {entry_id} marked as {resolution_status}",
            "entry_id": entry_id,
            "resolution_status": resolution_status,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Error resolving dead letter entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dead-letter/stats", response_model=DeadLetterStats)
async def get_dead_letter_stats(
    session: AsyncSession = Depends(get_session),
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
) -> DeadLetterStats:
    """
    Get statistics about the dead letter queue.
    
    Returns aggregated statistics for analysis and monitoring.
    """
    try:
        # Get basic counts
        counts_result = await session.execute(
            text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE archived_at >= NOW() - INTERVAL ':days days') as recent,
                    COUNT(*) FILTER (WHERE resolution_status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE resolution_status = 'resolved') as resolved,
                    COUNT(*) FILTER (WHERE resolution_status = 'investigating') as investigating,
                    COUNT(*) FILTER (WHERE resolution_status = 'ignored') as ignored
                FROM dead_letter_queue
            """),
            {"days": days},
        )
        counts = counts_result.mappings().first()
        
        # Get failure categories
        categories_result = await session.execute(
            text("""
                SELECT 
                    COALESCE(failure_category, 'unknown') as category,
                    COUNT(*) as count
                FROM dead_letter_queue
                WHERE archived_at >= NOW() - INTERVAL ':days days'
                GROUP BY failure_category
                ORDER BY count DESC
            """),
            {"days": days},
        )
        failure_categories = {
            row["category"]: row["count"] 
            for row in categories_result.mappings()
        }
        
        # Get job type distribution
        types_result = await session.execute(
            text("""
                SELECT 
                    job_type,
                    COUNT(*) as count
                FROM dead_letter_queue
                WHERE archived_at >= NOW() - INTERVAL ':days days'
                GROUP BY job_type
                ORDER BY count DESC
            """),
            {"days": days},
        )
        job_types = {
            row["job_type"]: row["count"] 
            for row in types_result.mappings()
        }
        
        # Get resolution time statistics
        time_stats_result = await session.execute(
            text("""
                SELECT 
                    COUNT(*) as total_resolved,
                    AVG(EXTRACT(EPOCH FROM (resolved_at - archived_at))) as avg_resolution_seconds,
                    MIN(EXTRACT(EPOCH FROM (resolved_at - archived_at))) as min_resolution_seconds,
                    MAX(EXTRACT(EPOCH FROM (resolved_at - archived_at))) as max_resolution_seconds
                FROM dead_letter_queue
                WHERE resolution_status = 'resolved'
                    AND resolved_at IS NOT NULL
                    AND archived_at >= NOW() - INTERVAL ':days days'
            """),
            {"days": days},
        )
        time_stats = time_stats_result.mappings().first()
        
        return DeadLetterStats(
            total_entries=counts["total"] if counts else 0,
            recent_entries=counts["recent"] if counts else 0,
            pending=counts["pending"] if counts else 0,
            resolved=counts["resolved"] if counts else 0,
            investigating=counts["investigating"] if counts else 0,
            ignored=counts["ignored"] if counts else 0,
            failure_categories=failure_categories,
            job_types=job_types,
            avg_resolution_seconds=float(time_stats["avg_resolution_seconds"] or 0) if time_stats else 0,
            min_resolution_seconds=float(time_stats["min_resolution_seconds"] or 0) if time_stats else 0,
            max_resolution_seconds=float(time_stats["max_resolution_seconds"] or 0) if time_stats else 0,
            analysis_period_days=days,
        )
        
    except Exception as e:
        logger.error(f"Error getting dead letter stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")