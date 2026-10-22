import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.limiter import limiter
from app.main import app
from app.models import Base

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to run API tests against a dedicated PostgreSQL database.",
)


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def get_test_session():
        async with session_factory() as session:
            yield session

    original_api_key = settings.API_KEY
    settings.API_KEY = "test-api-key"
    app.dependency_overrides[get_session] = get_test_session
    limiter._storage.reset()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client

    app.dependency_overrides.clear()
    settings.API_KEY = original_api_key
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def headers() -> dict[str, str]:
    return {"X-API-Key": "test-api-key"}


@pytest.mark.asyncio
async def test_create_and_list_jobs(client: httpx.AsyncClient):
    created = await client.post(
        "/jobs", headers=headers(), json={"type": "send_email", "payload": {"to": "a@example.com"}}
    )

    assert created.status_code == 201
    assert created.json()["status"] == "queued"

    listed = await client.get("/jobs", headers=headers())
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["jobs"][0]["id"] == created.json()["id"]


@pytest.mark.asyncio
async def test_create_job_requires_api_key(client: httpx.AsyncClient):
    response = await client.post("/jobs", json={"type": "send_email"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_job_rejects_invalid_type(client: httpx.AsyncClient):
    response = await client.post("/jobs", headers=headers(), json={"type": "unknown"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_job_rejects_payload_larger_than_4kb(client: httpx.AsyncClient):
    response = await client.post(
        "/jobs", headers=headers(), json={"type": "send_email", "payload": {"body": "x" * 4097}}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_job_rejects_invalid_and_missing_ids(client: httpx.AsyncClient):
    invalid = await client.get("/jobs/not-a-uuid", headers=headers())
    missing = await client.get(f"/jobs/{uuid4()}", headers=headers())

    assert invalid.status_code == 422
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_create_job_rate_limit(client: httpx.AsyncClient):
    responses = [
        await client.post("/jobs", headers=headers(), json={"type": "send_email"})
        for _ in range(31)
    ]

    assert all(response.status_code == 201 for response in responses[:30])
    assert responses[-1].status_code == 429
