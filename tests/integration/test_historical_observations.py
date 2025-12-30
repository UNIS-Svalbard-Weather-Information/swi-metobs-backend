import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.asyncio
class TestHistoricalObservationsEndpoints:
    """Test cases for historical observations endpoints."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    async def test_get_stations_with_historical_data(self, client):
        """Test getting stations with available historical data."""
        response = client.get("/v3/historical/available")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "TEST001" in data
    
    async def test_get_available_variables_for_station(self, client):
        """Test getting available variables for a station."""
        response = client.get("/v3/historical/TEST001/variables")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "temperature" in data
        assert "humidity" in data
    
    async def test_get_date_range_for_station(self, client):
        """Test getting date range for a station."""
        response = client.get("/v3/historical/TEST001/date-range")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "TEST001"
        assert "min_date" in data
        assert "max_date" in data
        assert "available_dates" in data
        assert isinstance(data["available_dates"], list)
    
    async def test_get_historical_data_for_station(self, client):
        """Test getting historical data for a station."""
        response = client.get("/v3/historical/TEST001?start_date=2023-01-01&end_date=2023-01-02")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "TEST001"
        assert "timeseries" in data
        assert len(data["timeseries"]) > 0
        assert "temperature" in data["timeseries"][0]
        assert "humidity" in data["timeseries"][0]
    
    async def test_get_historical_data_nonexistent_station(self, client):
        """Test getting historical data for non-existent station."""
        response = client.get("/v3/historical/NONEXISTENT/date-range")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"]
    
    async def test_get_historical_data_invalid_date_range(self, client):
        """Test getting historical data with invalid date range."""
        response = client.get("/v3/historical/TEST001?start_date=2024-01-01&end_date=2024-01-02")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "available" in data["detail"]
    
    async def test_get_historical_data_invalid_date_format(self, client):
        """Test getting historical data with invalid date format."""
        response = client.get("/v3/historical/TEST001?start_date=invalid-date&end_date=2023-01-02")
        assert response.status_code == 400  # Bad Request (custom error handling)
        data = response.json()
        assert "detail" in data