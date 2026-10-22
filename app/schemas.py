from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["send_email", "generate_report"]
    payload: dict = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    attempts: int
    max_retries: int
    last_error: str | None
    created_at: str
    updated_at: str


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


# Dead Letter Queue Schemas
class DeadLetterEntryBase(BaseModel):
    original_job_id: UUID
    job_type: str
    priority: int
    payload: dict
    metadata: dict
    final_error_type: str
    final_error_message: Optional[str] = None
    final_error_stack: Optional[str] = None
    final_attempt_count: int
    max_retries: int
    archived_reason: str
    failure_category: Optional[str] = None
    resolution_status: Optional[str] = "pending"
    resolution_notes: Optional[str] = None
    suggested_fix: Optional[str] = None


class DeadLetterEntryCreate(DeadLetterEntryBase):
    pass


class DeadLetterEntry(DeadLetterEntryBase):
    id: UUID
    archived_at: datetime
    created_at: datetime
    updated_at: datetime
    last_worker_id: Optional[str] = None
    last_processed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    original_job_created_at: Optional[datetime] = None
    original_job_started_at: Optional[datetime] = None
    original_job_finished_at: Optional[datetime] = None
    time_to_failure_seconds: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)


class DeadLetterStats(BaseModel):
    total_entries: int
    recent_entries: int
    pending: int
    resolved: int
    investigating: int
    ignored: int
    failure_categories: dict[str, int]
    job_types: dict[str, int]
    avg_resolution_seconds: float
    min_resolution_seconds: float
    max_resolution_seconds: float
    analysis_period_days: int


class ReprocessRequest(BaseModel):
    reason: str = Field(default="manual_reprocess", min_length=1, max_length=200)


class ResolveRequest(BaseModel):
    resolution_status: Literal["resolved", "ignored"] = "resolved"
    resolution_notes: str = Field(min_length=1, max_length=2000)


class ReprocessResponse(BaseModel):
    success: bool
    message: str
    new_job_id: UUID
    dead_letter_id: UUID


class CircuitBreakerStatus(BaseModel):
    failures: int
    threshold: int
    is_open: bool
    last_failure: Optional[str] = None
    time_since_last_failure: Optional[int] = None


class WorkerStats(BaseModel):
    circuit_breakers: dict[str, CircuitBreakerStatus]
    active_handlers: list[str]
    circuit_breaker_threshold: int
    circuit_breaker_reset_timeout: int