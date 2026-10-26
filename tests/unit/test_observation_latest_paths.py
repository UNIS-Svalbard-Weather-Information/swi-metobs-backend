import pytest
from fastapi import HTTPException

from app.api.v3.endpoints import observation_latest as latest


def test_offset_zero_is_the_latest_file():
    assert latest.resolve_data_file(0) == latest.LATEST_DATA_PATH


def test_every_valid_offset_resolves_inside_the_hourly_directory(monkeypatch):
    monkeypatch.setattr(latest, "enable_forecast", True)
    for offset in range(latest.MIN_TIME_OFFSET, latest.MAX_TIME_OFFSET + 1):
        if offset == 0:
            continue
        path = latest.resolve_data_file(offset)
        assert path == latest.HOURLY_DATA_DIR / f"{offset}.json"
        assert path.parent == latest.HOURLY_DATA_DIR


@pytest.mark.parametrize("offset", [-1000, -25, 25, 1000])
def test_out_of_range_offset_is_refused(monkeypatch, offset):
    monkeypatch.setattr(latest, "enable_forecast", True)
    with pytest.raises(HTTPException) as error:
        latest.resolve_data_file(offset)
    assert error.value.status_code == 400
    assert "out of range" in error.value.detail


def test_forecast_offset_refused_when_disabled(monkeypatch):
    monkeypatch.setattr(latest, "enable_forecast", False)
    with pytest.raises(HTTPException) as error:
        latest.resolve_data_file(1)
    assert error.value.status_code == 400
    assert error.value.detail == "Forecast data is not enabled"


def test_forecast_offset_allowed_when_enabled(monkeypatch):
    monkeypatch.setattr(latest, "enable_forecast", True)
    assert latest.resolve_data_file(24) == latest.HOURLY_DATA_DIR / "24.json"


@pytest.mark.parametrize("enabled, upper", [(False, 0), (True, 24)])
def test_out_of_range_message_matches_the_enabled_range(monkeypatch, enabled, upper):
    monkeypatch.setattr(latest, "enable_forecast", enabled)
    with pytest.raises(HTTPException) as error:
        latest.resolve_data_file(-25)
    assert f"between -24 and {upper}" in error.value.detail
