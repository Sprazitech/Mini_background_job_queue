from typing import Literal

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
