from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestForecastTimeseriesEndpoint:
    """The time-series endpoint against the latest AROME-Arctic run on THREDDS."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_returns_the_next_hours_at_longyearbyen_in_order(self, client):
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=6)
        response = client.get(
            "/v3/point-forecast/aa/surface/timeseries",
            params={
                "lat": 78.2232,
                "lon": 15.6267,
                "variables": ["air_temperature_2m", "wind_speed_10m"],
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        assert response.status_code == 200
        points = response.json()["timeseries"]
        assert 0 < len(points) <= 7
        times = [p["timestamp"] for p in points]
        assert times == sorted(times)
        for point in points:
            assert {"air_temperature_2m", "wind_speed_10m", "location"} <= point.keys()
            assert point["location"]["lat"] == pytest.approx(78.22, abs=0.05)
