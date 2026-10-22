import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.limiter import limiter
from app.models import Job
from app.schemas import JobCreate, JobListResponse, JobResponse
from app.security import verify_api_key

router = APIRouter(prefix="/jobs", tags=["jobs"])


def job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=str(job.id),
        type=job.type,
        status=job.status,
        attempts=job.attempts,
        max_retries=job.max_retries,
        last_error=job.last_error,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def create_job(
    request: Request,
    job_create: JobCreate,
    _: str = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    if len(json.dumps(job_create.payload)) > 4096:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payload exceeds 4KB")

    job = Job(
        type=job_create.type,
        payload=job_create.payload,
        status="queued",
        max_retries=settings.MAX_RETRIES,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job_response(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
) -> JobListResponse:
    filters = [Job.status == status_filter] if status_filter is not None else []
    total = await session.scalar(select(func.count()).select_from(Job).where(*filters))
    jobs = await session.scalars(
        select(Job)
        .where(*filters)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return JobListResponse(jobs=[job_response(job) for job in jobs], total=total or 0)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    _: str = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job_response(job)
