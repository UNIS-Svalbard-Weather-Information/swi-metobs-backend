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

    async def test_offset_lower_bound_reads_a_missing_file(self, client):
        """-24 is a valid offset: the request passes validation, the file is absent."""
        response = client.get("/v3/observations/stations/TEST001?offset=-24")
        assert response.status_code == 404
        assert response.json()["detail"] == "Data not found"

    async def test_offset_below_lower_bound(self, client):
        response = client.get("/v3/observations/stations/TEST001?offset=-25")
        assert response.status_code == 400
        assert "out of range" in response.json()["detail"]

    async def test_forecast_offset_refused_when_disabled(self, client):
        response = client.get("/v3/observations/stations/TEST001?offset=1")
        assert response.status_code == 400
        assert response.json()["detail"] == "Forecast data is not enabled"

    async def test_out_of_range_message_gives_the_real_upper_bound(self, client):
        """With forecast disabled the valid range is -24 to 0."""
        response = client.get("/v3/observations/stations/TEST001?offset=25")
        assert "between -24 and 0" in response.json()["detail"]

    @pytest.mark.parametrize(
        "offset, status",
        [(-25, 400), (25, 400), (1, 400), (-24, 404)],
    )
    async def test_all_stations_offset_validation(self, client, offset, status):
        response = client.get(f"/v3/observations/stations?offset={offset}")
        assert response.status_code == status

    @pytest.mark.parametrize("offset", ["../../etc/passwd", "-1/../0", "1.5", ""])
    async def test_non_integer_offset_is_rejected(self, client, offset):
        """The offset never reaches the filesystem unless it is an integer."""
        response = client.get("/v3/observations/stations", params={"offset": offset})
        assert response.status_code == 422

    async def test_station_without_data_for_the_hour_returns_empty_timeseries(
        self, client
    ):
        """The caching job stores null when a station has no data for an hour."""
        response = client.get("/v3/observations/stations/NULL001?offset=-1")
        assert response.status_code == 200
        assert response.json() == {"id": "NULL001", "timeseries": []}

    async def test_all_stations_with_a_null_timeseries(self, client):
        """One station without data must not fail the whole listing."""
        response = client.get("/v3/observations/stations?offset=-1")
        assert response.status_code == 200
        by_id = {s["id"]: s for s in response.json()}
        assert by_id["NULL001"]["timeseries"] == []
        assert len(by_id["TEST001"]["timeseries"]) > 0
