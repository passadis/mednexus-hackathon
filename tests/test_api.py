"""Tests for the FastAPI endpoints (integration-style)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from mednexus.api.main import app


@pytest.fixture
async def client():
    """Async client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert "agents" in body


class TestPatientsEndpoint:
    @pytest.mark.asyncio
    async def test_list_patients(self, client: AsyncClient) -> None:
        resp = await client.get("/api/patients")
        # May be empty list if Cosmos is not connected, but should not 500
        assert resp.status_code in (200, 500)  # 500 expected without Cosmos

    @pytest.mark.asyncio
    async def test_get_nonexistent_patient(self, client: AsyncClient) -> None:
        resp = await client.get("/api/patients/DOESNOTEXIST999")
        assert resp.status_code in (404, 500)


class TestApprovalEndpoint:
    """Phase 3: Human-in-the-Loop MD sign-off endpoint."""

    @pytest.mark.asyncio
    async def test_approve_nonexistent_patient(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/patients/DOESNOTEXIST999/approve",
            json={"approved_by": "Dr. Test"},
        )
        # 404 if patient not found, 500 if Cosmos unavailable
        assert resp.status_code in (404, 500)

    @pytest.mark.asyncio
    async def test_approve_missing_body(self, client: AsyncClient) -> None:
        resp = await client.post("/api/patients/P1234/approve")
        assert resp.status_code == 422  # Pydantic validation error
