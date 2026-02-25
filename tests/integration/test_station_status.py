import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.asyncio
class TestStationStatusEndpoints:
    """Test cases for station status endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    async def test_get_all_stations(self, client):
        """Test getting all stations."""
        response = client.get("/v3/station-status/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "TEST001" in data
        assert data["TEST001"]["id"] == "TEST001"
        assert data["TEST001"]["name"] == "Test Station"

    async def test_get_online_stations(self, client):
        """Test getting online stations."""
        response = client.get("/v3/station-status/online")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "TEST001" in data
        assert data["TEST001"]["status"] == "online"

    async def test_get_offline_stations(self, client):
        """Test getting offline stations."""
        response = client.get("/v3/station-status/offline")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert len(data) == 0  # No offline stations in test data

    async def test_get_specific_station(self, client):
        """Test getting a specific station."""
        response = client.get("/v3/station-status/TEST001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "TEST001"
        assert data["name"] == "Test Station"
        assert data["type"] == "fixed"
        assert data["status"] == "online"

    async def test_get_nonexistent_station(self, client):
        """Test getting a non-existent station."""
        response = client.get("/v3/station-status/NONEXISTENT")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"]

    async def test_invalid_station_id_format(self, client):
        """Test getting station with invalid ID format."""
        response = client.get("/v3/station-status/invalid@station")
        assert response.status_code == 400  # Bad Request (custom error handling)
        data = response.json()
        assert "detail" in data

    async def test_search_stations(self, client):
        """Test searching for stations by name."""
        response = client.get("/v3/station-status/search?q=Test")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0
        # Check that the result contains the test station
        assert any(station["id"] == "TEST001" for station in data["items"])

    async def test_search_stations_limit(self, client):
        """Test searching for stations with limit parameter."""
        response = client.get("/v3/station-status/search?q=Test&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) <= 5

    async def test_search_stations_no_results(self, client):
        """Test searching for stations with no results."""
        response = client.get("/v3/station-status/search?q=xyzabc123notfound")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 0

    async def test_search_stations_empty_query(self, client):
        """Test searching for stations with empty query."""
        response = client.get("/v3/station-status/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
