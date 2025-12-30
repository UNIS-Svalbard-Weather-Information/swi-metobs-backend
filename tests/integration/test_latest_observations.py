import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.asyncio
class TestLatestObservationsEndpoints:
    """Test cases for latest observations endpoints."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    async def test_get_specific_station_observations(self, client):
        """Test getting observations for a specific station."""
        response = client.get("/v3/observations/stations/TEST001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "TEST001"
        assert "timeseries" in data
        assert len(data["timeseries"]) > 0
        assert "temperature" in data["timeseries"][0]
        assert "humidity" in data["timeseries"][0]
    
    async def test_get_all_stations_observations(self, client):
        """Test getting observations for all stations."""
        response = client.get("/v3/observations/stations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["id"] == "TEST001"
    
    async def test_get_nonexistent_station_observations(self, client):
        """Test getting observations for a non-existent station."""
        response = client.get("/v3/observations/stations/NONEXISTENT")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"]
    
    async def test_invalid_station_id_format_observations(self, client):
        """Test getting observations with invalid station ID format."""
        response = client.get("/v3/observations/stations/invalid@station")
        assert response.status_code == 400  # Bad Request (custom error handling)
        data = response.json()
        assert "detail" in data
    
    async def test_offset_out_of_range(self, client):
        """Test getting observations with offset out of range."""
        response = client.get("/v3/observations/stations/TEST001?offset=25")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "out of range" in data["detail"]