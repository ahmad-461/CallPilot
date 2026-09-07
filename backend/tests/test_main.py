import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_disconnected():
    """When DB credentials are not configured or connection fails, /health returns 503."""
    with patch("app.main.check_db_connection", return_value=(False, "Connection error")):
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "error", "db": "disconnected"}


def test_health_check_connected():
    """When DB connection succeeds, /health returns 200."""
    with patch("app.main.check_db_connection", return_value=(True, "connected")):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "db": "connected"}


@pytest.mark.parametrize("prefix", ["/calls", "/appointments"])
def test_router_stubs(prefix):
    """Router stubs return 501 Not Implemented."""
    response = client.get(prefix)
    assert response.status_code == 501
    assert response.json() == {"detail": f"{prefix[1:].capitalize()} API endpoints are not implemented yet."}
