"""Test API endpoints."""

from fastapi.testclient import TestClient


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
