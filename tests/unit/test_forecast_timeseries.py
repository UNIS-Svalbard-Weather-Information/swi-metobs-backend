"""Point forecast time series: every hour of a range in one dataset read."""

from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from app.api.v3.endpoints.forecast_model.model_aa import (
    ModelAromeArctic,
    ModelAromeArcticConnector,
)
from app.main import app

HOURS = pd.date_range("2026-10-04T12:00", periods=6, freq="h")


def model_dataset() -> xr.Dataset:
    """A 2 x 2 grid with six hourly steps, shaped like the THREDDS dataset."""
    shape = (len(HOURS), 2, 2)
    return xr.Dataset(
        {
            "air_temperature_2m": (
                ("time", "y", "x"),
                np.arange(24.0).reshape(shape),
                {"units": "degC"},
            ),
            "wind_speed": (("time", "y", "x"), np.full(shape, 5.0), {"units": "m/s"}),
        },
        coords={
            "time": HOURS.values,
            "x": [0.0, 2500.0],
            "y": [0.0, 2500.0],
            "latitude": (("y", "x"), [[78.0, 78.0], [78.02, 78.02]]),
            "longitude": (("y", "x"), [[15.0, 15.1], [15.0, 15.1]]),
        },
    )


@pytest.fixture
def connector():
    conn = ModelAromeArcticConnector()
    saved = (conn.ds, conn.ds_grid)
    conn.ds = model_dataset()
    conn.ds_grid = conn.ds[["x", "y"]]
    conn.get_subset_range.cache_clear()
    yield conn
    conn.get_subset_range.cache_clear()
    conn.ds, conn.ds_grid = saved


class TestConnectorRange:
    def test_reads_every_hour_of_the_range_at_the_nearest_grid_point(self, connector):
        subset = connector.get_subset_range(
            x=2400.0,
            y=100.0,
            start=datetime(2026, 10, 4, 13),
            end=datetime(2026, 10, 4, 16),
            variables=frozenset({"air_temperature_2m"}),
        )
        assert list(pd.to_datetime(subset.time.values).hour) == [13, 14, 15, 16]
        # Grid point y=0, x=2500: index 1 of each 2 x 2 step.
        assert list(subset["air_temperature_2m"].values) == [5.0, 9.0, 13.0, 17.0]
        assert float(subset.longitude) == pytest.approx(15.1)

    def test_rejects_a_point_outside_the_grid(self, connector):
        with pytest.raises(ValueError, match="km"):
            connector.get_subset_range(
                x=50_000.0,
                y=0.0,
                start=HOURS[0].to_pydatetime(),
                end=HOURS[-1].to_pydatetime(),
                variables=frozenset({"air_temperature_2m"}),
            )


class TestModelSeries:
    def test_asks_the_connector_once_for_the_whole_range(self, monkeypatch):
        calls = []

        def fake_range(self, x, y, start, end, variables):
            calls.append((start, end, variables))
            return model_dataset().isel(x=0, y=0)

        monkeypatch.setattr(ModelAromeArcticConnector, "get_subset_range", fake_range)
        start, end = datetime(2026, 10, 4, 12), datetime(2026, 10, 4, 17)
        model = ModelAromeArctic(latitude=78.2, longitude=15.6, time=start)
        ds = model.get_surface_series(["air_temperature_2m"], start=start, end=end)

        assert len(calls) == 1
        assert calls[0][:2] == (start, end)
        assert calls[0][2] == frozenset({"air_temperature_2m"})
        assert list(ds.data_vars) == ["air_temperature_2m"]
        assert ds.sizes["time"] == 6

    def test_rejects_an_unknown_variable(self):
        start = datetime(2026, 10, 4, 12)
        model = ModelAromeArctic(latitude=78.2, longitude=15.6, time=start)
        with pytest.raises(ValueError, match="not available"):
            model.get_surface_series(["snow"], start=start, end=start)


class TestTimeseriesEndpoint:
    URL = "/v3/point-forecast/aa/surface/timeseries"

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def series(self, monkeypatch):
        mock = MagicMock(
            side_effect=lambda variable, start, end: (
                model_dataset().isel(x=0, y=0).sel(time=slice(start, end))[variable]
            )
        )
        monkeypatch.setattr(
            ModelAromeArctic,
            "get_surface_series",
            lambda self, variable, start, end: mock(variable, start, end),
        )
        return mock

    def query(self, **overrides):
        params = {
            "lat": 78.0,
            "lon": 15.0,
            "variables": ["air_temperature_2m"],
            "start": "2026-10-04T13:00:00.000Z",
            "end": "2026-10-04T15:00:00.000Z",
        }
        params.update(overrides)
        return params

    def test_returns_every_hour_with_the_grid_point(self, client, series):
        response = client.get(self.URL, params=self.query())
        assert response.status_code == 200
        points = response.json()["timeseries"]
        assert [p["timestamp"] for p in points] == [
            "2026-10-04T13:00:00",
            "2026-10-04T14:00:00",
            "2026-10-04T15:00:00",
        ]
        assert points[0]["location"] == {"lat": 78.0, "lon": 15.0}
        assert points[0]["air_temperature_2m"] == 4.0

    def test_reads_times_as_utc(self, client, series):
        client.get(self.URL, params=self.query(start="2026-10-04T15:00:00+02:00"))
        _, start, _ = series.call_args.args
        assert start == datetime(2026, 10, 4, 13)

    def test_answers_an_empty_series_for_a_range_without_forecast(self, client, series):
        response = client.get(
            self.URL,
            params=self.query(start="2026-10-05T00:00:00Z", end="2026-10-05T03:00:00Z"),
        )
        assert response.status_code == 200
        assert response.json()["timeseries"] == []

    @pytest.mark.parametrize(
        "overrides",
        [
            {"start": "yesterday"},
            {"start": "2026-10-04T15:00:00Z", "end": "2026-10-04T13:00:00Z"},
            {"end": "2026-10-10T13:00:00Z"},
        ],
    )
    def test_rejects_an_invalid_range(self, client, series, overrides):
        assert client.get(self.URL, params=self.query(**overrides)).status_code == 400

    def test_rejects_an_unknown_model(self, client, series):
        response = client.get(
            "/v3/point-forecast/unknown/surface/timeseries", params=self.query()
        )
        assert response.status_code == 404

    def test_reports_an_unknown_variable(self, client, monkeypatch):
        response = client.get(self.URL, params=self.query(variables=["snow"]))
        assert response.status_code == 400
