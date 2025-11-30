"""Tests for API endpoints."""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from trading_journal.services.execution_service import ExecutionService


def test_root_endpoint(client: TestClient):
    """Test root endpoint returns expected data."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Trading Journal"
    assert data["status"] == "running"
    assert "version" in data


def test_health_endpoint(client: TestClient):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_list_executions_empty(client: TestClient):
    """Test listing executions when none exist."""
    response = client.get("/api/v1/executions")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["executions"] == []


@pytest.mark.asyncio
async def test_get_execution_not_found(client: TestClient):
    """Test getting non-existent execution."""
    response = client.get("/api/v1/executions/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_trades_empty(client: TestClient):
    """Test listing trades when none exist."""
    response = client.get("/api/v1/trades")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["trades"] == []


@pytest.mark.asyncio
async def test_get_trade_not_found(client: TestClient):
    """Test getting non-existent trade."""
    response = client.get("/api/v1/trades/9999")
    assert response.status_code == 404
