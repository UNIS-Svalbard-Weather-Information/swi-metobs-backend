import pytest
from datetime import datetime
from app.api.v3.endpoints.forecast_model.model import (
    reproject_variable,
    compute_wind_direction,
    compute_wind_speed,
    _select_variables,
    update_history,
)
from app.models.forecast import ForecastModelInfo
import numpy as np


class TestWeatherModel:
    """Test cases for WeatherModel abstract base class."""

    def test_forecast_model_info_resolution_transform(self):
        """Test resolution transformation in ForecastModelInfo."""
        # Test integer resolution gets transformed to km
        model_info = ForecastModelInfo(
            id="test",
            name="Test Model",
            provider="Test Provider",
            resolution=2500,  # 2.5 km
        )
        assert model_info.resolution == "2.5km"

        # Test string resolution stays as is
        model_info = ForecastModelInfo(
            id="test", name="Test Model", provider="Test Provider", resolution="2.5km"
        )
        assert model_info.resolution == "2.5km"


class TestForecastModelFunctions:
    """Test cases for forecast model utility functions."""

    def test_reproject_variable_basic(self):
        """Test basic variable reprojection."""
        # Test with None projection (should return original values)
        x = np.array([1.0, 2.0])
        y = np.array([3.0, 4.0])
        result_x, result_y = reproject_variable(x, y)
        np.testing.assert_array_equal(result_x, x)
        np.testing.assert_array_equal(result_y, y)

    def test_reproject_variable_with_projection(self):
        """Test variable reprojection with projection parameters."""
        # Create a simple projection dictionary
        projection = {
            "latitude_of_projection_origin": 77.5,
            "longitude_of_central_meridian": -25.0,
        }

        x = np.array([1.0, 2.0])
        y = np.array([3.0, 4.0])

        # Test with projection but no longitude/latitude (should return original)
        result_x, result_y = reproject_variable(x, y, projection=projection)
        np.testing.assert_array_equal(result_x, x)
        np.testing.assert_array_equal(result_y, y)

    def test_compute_wind_direction(self):
        """Test wind direction computation."""
        # Test basic wind direction calculation
        # Note: metpy functions require units, so we need to use metpy.quantify
        from metpy.units import units

        # In meteorology, u is west-east (east is positive), v is south-north (north is positive)
        u = np.array([1.0, 0.0]) * units("m/s")  # East wind (270 degrees "from")
        v = np.array([0.0, 1.0]) * units("m/s")  # North wind (180 degrees "from")

        result = compute_wind_direction(u, v)
        # East wind should give 270 degrees "from", North wind should give 180 degrees "from"
        expected = np.array([270.0, 180.0])
        np.testing.assert_array_almost_equal(result, expected, decimal=5)

    def test_compute_wind_speed(self):
        """Test wind speed computation."""
        # Test basic wind speed calculation
        # Note: metpy functions require units, so we need to use metpy.quantify
        from metpy.units import units

        u = np.array([3.0, 4.0]) * units("m/s")  # 3 m/s east
        v = np.array([4.0, 3.0]) * units("m/s")  # 4 m/s north

        result = compute_wind_speed(u, v)
        # Should give 5 m/s and 5 m/s
        expected = np.array([5.0, 5.0])
        np.testing.assert_array_almost_equal(result, expected, decimal=5)

    def test_select_variables(self):
        """Test variable selection function."""
        # Create a mock variables_available dictionary
        variables_available = {
            "temp": {"model_variable": ["temperature"]},
            "wind": {"model_variable": ["u_wind", "v_wind"]},
            "pressure": {"model_variable": ["surface_pressure"]},
        }

        # Test selecting single variable
        result = _select_variables(["temp"], variables_available)
        assert result == ["temperature"]

        # Test selecting multiple variables
        result = _select_variables(["temp", "wind"], variables_available)
        assert set(result) == {"temperature", "u_wind", "v_wind"}

        # Test selecting all variables
        result = _select_variables(["temp", "wind", "pressure"], variables_available)
        assert set(result) == {"temperature", "u_wind", "v_wind", "surface_pressure"}

    def test_select_variables_invalid(self):
        """Test variable selection with invalid variable."""
        variables_available = {"temp": {"model_variable": ["temperature"]}}

        # Test with invalid variable
        with pytest.raises(ValueError) as exc_info:
            _select_variables(["invalid_var"], variables_available)

        assert "Requested variable 'invalid_var' is not available in the model" in str(
            exc_info.value
        )

    def test_update_history(self):
        """Test update_history function."""
        import xarray as xr

        # Create a simple dataset
        ds = xr.Dataset()

        # Update history
        updated_ds = update_history(ds, "Test information")

        # Check that history was added
        assert "history" in updated_ds.attrs
        assert "Test information" in updated_ds.attrs["history"]
        assert "sw-swi-srm_swi-metobs-backend::" in updated_ds.attrs["history"]


class TestModelAromeArctic:
    """Test cases for ModelAromeArctic class."""

    def test_model_arome_arctic_initialization(self):
        """Test ModelAromeArctic initialization."""
        from app.api.v3.endpoints.forecast_model.model_aa import ModelAromeArctic

        # Test basic initialization
        model = ModelAromeArctic(longitude=-25.0, latitude=78.0, time=datetime.now())

        assert model.longitude == -25.0
        assert model.latitude == 78.0
        assert model.time is not None
        assert model.x is not None
        assert model.y is not None

        # Test class attributes
        assert model.name == "Arome Arctic"
        assert model.provider == "Norwegian Meteorological Institute"
        assert model.resolution == 2500
        assert "grid_mapping_name" in model.projection
        assert len(model.variables_surface) > 0
        assert len(model.variables_profile) > 0

    def test_model_arome_arctic_xy_conversion(self):
        """Test latitude/longitude to x/y conversion."""
        from app.api.v3.endpoints.forecast_model.model_aa import ModelAromeArctic

        # Test coordinate conversion
        model = ModelAromeArctic(longitude=-25.0, latitude=78.0, time=datetime.now())

        # The x and y should be calculated based on the projection
        assert isinstance(model.x, float)
        assert isinstance(model.y, float)

        # For the Arome Arctic projection, these should be reasonable values
        # around the projection origin
        assert abs(model.x) < 1e6
        assert abs(model.y) < 1e6

    def test_model_arome_arctic_variables_structure(self):
        """Test that ModelAromeArctic has expected variable structure."""
        from app.api.v3.endpoints.forecast_model.model_aa import ModelAromeArctic

        # Test surface variables
        assert "air_temperature_2m" in ModelAromeArctic.variables_surface
        assert "wind_speed_10m" in ModelAromeArctic.variables_surface
        assert "wind_direction_10m" in ModelAromeArctic.variables_surface
        assert "surface_pressure" in ModelAromeArctic.variables_surface

        # Test profile variables
        assert "air_temperature" in ModelAromeArctic.variables_profile
        assert "wind_speed" in ModelAromeArctic.variables_profile
        assert "wind_direction" in ModelAromeArctic.variables_profile
        assert "dew_point_temperature" in ModelAromeArctic.variables_profile
        assert "relative_humidity" in ModelAromeArctic.variables_profile
        assert "specific_humidity" in ModelAromeArctic.variables_profile

        # Test that each variable has required fields
        for var_name, var_info in ModelAromeArctic.variables_surface.items():
            assert "unit" in var_info
            assert "description" in var_info
            assert "model_variable" in var_info
            assert "function" in var_info

        for var_name, var_info in ModelAromeArctic.variables_profile.items():
            assert "unit" in var_info
            assert "description" in var_info
            assert "model_variable" in var_info
            assert "function" in var_info
