from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import Task
from app.db.session import get_db_session
from app.main import app


@pytest.fixture(autouse=True)
def mock_worker():
    with patch("app.api.v1.tasks.WorkerService.enqueue_task") as mock:
        yield mock

@pytest.mark.asyncio
async def test_health_check() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_create_task() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "url": "https://example.com",
            "objective": "Find all products",
            "schema_definition": {
                "name": "string",
                "price": "number"
            }
        }

        response = await client.post("/api/v1/tasks", json=payload)
        assert response.status_code == 202

        data = response.json()
        assert "id" in data
        assert data["url"] == "https://example.com/"
        assert data["goal"] == payload["objective"]
        assert data["status"] == "QUEUED"

        task_id = data["id"]

        # Verify it exists in DB
        async with get_db_session() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            assert task.url == "https://example.com/"

@pytest.mark.asyncio
async def test_get_task() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "url": "https://example.com",
            "objective": "Test Get"
        }

        create_resp = await client.post("/api/v1/tasks", json=payload)
        task_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 200

        data = get_resp.json()
        assert data["id"] == task_id
        assert data["goal"] == "Test Get"

@pytest.mark.asyncio
async def test_cancel_task() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "url": "https://example.com",
            "objective": "Test Cancel"
        }

        create_resp = await client.post("/api/v1/tasks", json=payload)
        task_id = create_resp.json()["id"]

        cancel_resp = await client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert cancel_resp.status_code == 200

        data = cancel_resp.json()
        assert data["status"] == "CANCELLED"

        # Trying to cancel again should fail or just return the cancelled task?
        # Our endpoint says: if task.status in ["COMPLETED", "FAILED", "CANCELLED"]: raise 400
        cancel_again_resp = await client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert cancel_again_resp.status_code == 400

@pytest.mark.asyncio
async def test_get_task_not_found() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/tasks/non-existent-id")
        assert response.status_code == 404
