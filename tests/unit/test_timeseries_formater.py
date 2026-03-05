import pytest
import pandas as pd
import xarray as xr
from app.utils.timeseries_formater import format_xarray_to_timeseries


class TestTimeseriesFormater:
    """Test cases for timeseries formatting functions."""

    def test_format_xarray_to_timeseries_basic(self):
        """Test basic timeseries formatting with time dimension only."""
        # Create a simple dataset with time dimension
        time_values = pd.date_range("2023-01-01", periods=3, freq="h")
        ds = xr.Dataset(
            {
                "temperature": (["time"], [15.0, 16.0, 17.0]),
                "humidity": (["time"], [60.0, 65.0, 70.0]),
            },
            coords={"time": time_values, "latitude": 45.0, "longitude": 6.0},
        )

        # Format to timeseries
        result = format_xarray_to_timeseries(ds, station_id="test_station")

        # Check result structure
        assert result.id == "test_station"
        assert len(result.timeseries) == 3

        # Check first data point
        first_point = result.timeseries[0]
        assert first_point.timestamp == pd.Timestamp("2023-01-01 00:00:00")
        assert first_point.location == {"lat": 45.0, "lon": 6.0}
        assert first_point.temperature == 15.0
        assert first_point.humidity == 60.0

    def test_format_xarray_to_timeseries_with_z_dimension(self):
        """Test timeseries formatting with both time and z dimensions."""
        # Create a dataset with time and z dimensions
        time_values = pd.date_range("2023-01-01", periods=2, freq="h")
        z_values = [0, 10, 20]  # height levels

        ds = xr.Dataset(
            {
                "temperature": (
                    ["time", "z"],
                    [[15.0, 14.0, 13.0], [16.0, 15.0, 14.0]],
                ),
                "wind_speed": (["time", "z"], [[5.0, 6.0, 7.0], [4.0, 5.0, 6.0]]),
            },
            coords={
                "time": time_values,
                "z": z_values,
                "latitude": 78.0,
                "longitude": -25.0,
            },
        )

        # Format to timeseries
        result = format_xarray_to_timeseries(ds, station_id="test_profile")

        # Check result structure - should have time * z combinations
        assert result.id == "test_profile"
        assert len(result.timeseries) == 6  # 2 times * 3 heights

        # Check that all combinations are present
        timestamps = [point.timestamp for point in result.timeseries]
        assert len(set(timestamps)) == 2  # 2 unique timestamps

    def test_format_xarray_to_timeseries_z_only(self):
        """Test timeseries formatting with z dimension only (no time dimension)."""
        # Create a dataset with z dimension only
        z_values = [0, 10, 20, 30]

        ds = xr.Dataset(
            {
                "temperature": (["z"], [15.0, 14.0, 13.0, 12.0]),
                "pressure": (["z"], [1013.0, 950.0, 900.0, 850.0]),
            },
            coords={
                "z": z_values,
                "time": pd.Timestamp("2023-01-01 12:00:00"),
                "latitude": 78.5,
                "longitude": -24.5,
            },
        )

        # Format to timeseries
        result = format_xarray_to_timeseries(ds, station_id="test_sounding")

        # Check result structure
        assert result.id == "test_sounding"
        assert len(result.timeseries) == 4  # 4 height levels

        # All points should have the same timestamp
        timestamps = [point.timestamp for point in result.timeseries]
        assert all(t == pd.Timestamp("2023-01-01 12:00:00") for t in timestamps)

    def test_format_xarray_to_timeseries_auto_id_generation(self):
        """Test automatic station ID generation."""
        # Create a simple dataset
        ds = xr.Dataset(
            {"temperature": (["time"], [15.0, 16.0])},
            coords={
                "time": pd.date_range("2023-01-01", periods=2, freq="h"),
                "latitude": 78.1234,
                "longitude": -25.5678,
            },
        )

        # Format without specifying station_id
        result = format_xarray_to_timeseries(ds)

        # Check that ID was generated correctly
        assert result.id == "forecast_model_at_781234_-255678"

    def test_format_xarray_to_timeseries_data_types(self):
        """Test that data types are preserved correctly."""
        # Create dataset with various data types
        ds = xr.Dataset(
            {
                "temperature": (["time"], [15.123456, 16.987654]),
                "humidity": (["time"], [60.5, 65.7]),
                "pressure": (["time"], [1013.25, 1012.75]),
            },
            coords={
                "time": pd.date_range("2023-01-01", periods=2, freq="h"),
                "latitude": 45.1234,
                "longitude": 6.5678,
            },
        )

        # Format to timeseries
        result = format_xarray_to_timeseries(ds, station_id="test_types")

        # Check that values are rounded to 3 decimal places
        first_point = result.timeseries[0]
        assert first_point.temperature == 15.123
        assert first_point.humidity == 60.5
        assert first_point.pressure == 1013.25

    def test_format_xarray_to_timeseries_location_rounding(self):
        """Test that location coordinates are rounded correctly."""
        # Create dataset with precise coordinates
        ds = xr.Dataset(
            {"temperature": (["time"], [15.0])},
            coords={
                "time": [pd.Timestamp("2023-01-01 12:00:00")],
                "latitude": 78.123456789,
                "longitude": -25.987654321,
            },
        )

        # Format to timeseries
        result = format_xarray_to_timeseries(ds, station_id="test_location")

        # Check that location is rounded to 4 decimal places
        first_point = result.timeseries[0]
        assert first_point.location == {"lat": 78.1235, "lon": -25.9877}

    def test_format_xarray_to_timeseries_missing_dimensions(self):
        """Test error handling for missing required dimensions."""
        # Create dataset without time or z dimensions
        ds = xr.Dataset(
            {"temperature": ([], 15.0)}, coords={"latitude": 45.0, "longitude": 6.0}
        )

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            format_xarray_to_timeseries(ds)

        assert "Dataset must contain 'z' or 'time' dimensions for formatting" in str(
            exc_info.value
        )

    def test_format_xarray_to_timeseries_empty_dataset(self):
        """Test handling of empty dataset."""
        # Create empty dataset with proper dimensions
        ds = xr.Dataset(coords={"time": [], "latitude": 45.0, "longitude": 6.0})

        # Should handle gracefully
        result = format_xarray_to_timeseries(ds, station_id="empty_test")

        assert result.id == "empty_test"
        assert len(result.timeseries) == 0

    def test_format_xarray_to_timeseries_single_data_point(self):
        """Test formatting of single data point."""
        # Create dataset with single time point
        ds = xr.Dataset(
            {"temperature": (["time"], [15.5]), "wind_speed": (["time"], [3.2])},
            coords={
                "time": [pd.Timestamp("2023-01-01 12:00:00")],
                "latitude": 78.0,
                "longitude": -25.0,
            },
        )

        # Format to timeseries
        result = format_xarray_to_timeseries(ds, station_id="single_point")

        # Check result
        assert result.id == "single_point"
        assert len(result.timeseries) == 1

        point = result.timeseries[0]
        assert point.timestamp == pd.Timestamp("2023-01-01 12:00:00")
        assert point.temperature == 15.5
        assert point.wind_speed == 3.2
