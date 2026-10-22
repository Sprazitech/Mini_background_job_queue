from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.config import settings
from app.health import router as health_router
from app.limiter import limiter
from app.routes.jobs import router as jobs_router
from app.worker.loop import start_worker, stop_worker


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = await start_worker() if settings.WORKER_ENABLED else None
    yield
    if task:
        await stop_worker(task)


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://job-queue-docs.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs_router)
app.include_router(health_router)
