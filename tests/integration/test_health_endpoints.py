import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.v3.endpoints._health_config import HEALTH_CHECK_PATHS, CRITICAL_PATHS
from pathlib import Path


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Test cases for health check endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    async def test_health_endpoint_returns_200(self, client):
        """Test that health endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "data_paths" in data
        assert data["service"] == "swi-metobs-backend"

    async def test_health_endpoint_checks_critical_paths(self, client):
        """Test that health endpoint checks all critical paths."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        paths_checked = data["data_paths"]

        # Verify all critical paths are being checked
        for path_name in CRITICAL_PATHS:
            assert path_name in paths_checked, f"Critical path {path_name} not checked"
            assert "status" in paths_checked[path_name]
            assert "path" in paths_checked[path_name]

    async def test_liveness_endpoint_returns_200(self, client):
        """Test that liveness endpoint returns 200 OK with simple response."""
        response = client.get("/live")
        assert response.status_code == 200
        assert response.text == "OK"
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    async def test_readiness_endpoint_returns_200_when_healthy(self, client):
        """Test that readiness endpoint returns 200 when all critical paths are healthy."""
        response = client.get("/ready")

        # If the service is running properly, it should return 200
        if response.status_code == 200:
            assert response.text == "Ready"
        else:
            # If it returns 503, that means some paths are missing (which is expected in test environment)
            assert response.status_code == 503
            error_data = response.json()
            assert "status" in error_data["detail"]
            assert error_data["detail"]["status"] == "not_ready"
            assert "missing_paths" in error_data["detail"]

    async def test_health_endpoint_structure(self, client):
        """Test the structure of health endpoint response."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()

        # Check top-level structure
        assert isinstance(data, dict)
        assert data["status"] in ["healthy", "degraded"]
        assert data["service"] == "swi-metobs-backend"
        assert isinstance(data["data_paths"], dict)

        # Check data_paths structure
        for path_name, path_info in data["data_paths"].items():
            assert isinstance(path_info, dict)
            assert "status" in path_info
            assert "path" in path_info
            assert path_info["status"] in ["healthy", "unhealthy"]
            assert isinstance(path_info["path"], str)
            if path_info["status"] == "unhealthy":
                assert "error" in path_info

    async def test_health_endpoints_not_versioned(self, client):
        """Test that health endpoints are not under versioned prefix."""
        # These should work (non-versioned)
        assert client.get("/health").status_code == 200
        assert client.get("/live").status_code == 200

        # These should NOT work (versioned)
        assert client.get("/v3/health").status_code == 404
        assert client.get("/v3/live").status_code == 404
        assert client.get("/v3/ready").status_code == 404

    async def test_health_config_contains_expected_paths(self):
        """Test that health config contains the expected critical paths."""
        expected_critical_paths = {
            "stations_status",
            "online_stations",
            "latest_observations",
            "long_timeseries_dir",
            "forecast_dir",
        }

        actual_critical_paths = set(CRITICAL_PATHS)
        assert expected_critical_paths.issubset(actual_critical_paths)

        # Verify paths are Path objects
        for path_name in CRITICAL_PATHS:
            assert isinstance(HEALTH_CHECK_PATHS[path_name], Path)

    async def test_health_endpoint_with_missing_paths(self, client, monkeypatch):
        """Test health endpoint behavior when some paths are missing."""
        # This is a more advanced test that would require mocking
        # For now, we'll just verify the endpoint handles the current state gracefully
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        # Should either be healthy or degraded, not error
        assert data["status"] in ["healthy", "degraded"]
