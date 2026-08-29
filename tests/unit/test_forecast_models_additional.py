import threading
import numpy as np
import pytest
import xarray as xr
from datetime import datetime
from unittest.mock import MagicMock
from app.api.v3.endpoints.forecast_model.model import (
    reproject_variable,
    compute_wind_direction,
    compute_wind_speed,
    _select_variables,
    update_history,
)
from metpy.units import units


class TestForecastModelAdditionalCoverage:
    """Additional test cases to improve coverage for forecast model functions."""

    def test_reproject_variable_with_full_projection(self):
        """Test reproject_variable with complete projection parameters."""
        # Create a complete projection dictionary
        projection = {
            "latitude_of_projection_origin": 77.5,
            "longitude_of_central_meridian": -25.0,
        }

        x = np.array([100.0, 200.0])
        y = np.array([300.0, 400.0])

        # Test with all parameters
        result_x, result_y = reproject_variable(
            x, y, projection=projection, longitude=-25.0, latitude=78.0
        )

        # Should return reprojected values
        assert result_x is not None
        assert result_y is not None
        assert len(result_x) == 2
        assert len(result_y) == 2

    def test_reproject_variable_edge_cases(self):
        """Test reproject_variable with edge cases."""
        projection = {
            "latitude_of_projection_origin": 0.0,  # Equator
            "longitude_of_central_meridian": 0.0,
        }

        # Test with zero values
        x = np.array([0.0])
        y = np.array([0.0])
        result_x, result_y = reproject_variable(
            x, y, projection=projection, longitude=0.0, latitude=0.0
        )
        assert result_x[0] == 0.0
        assert result_y[0] == 0.0

    def test_compute_wind_functions_with_projection(self):
        """Test wind computation functions with projection reprojection."""
        projection = {
            "latitude_of_projection_origin": 77.5,
            "longitude_of_central_meridian": -25.0,
        }

        # Create wind components with units
        u = np.array([10.0, 5.0]) * units("m/s")
        v = np.array([0.0, 10.0]) * units("m/s")

        # Test wind direction with projection
        dir_result = compute_wind_direction(
            u, v, projection=projection, longitude=-25.0, latitude=78.0
        )
        assert len(dir_result) == 2

        # Test wind speed with projection
        speed_result = compute_wind_speed(
            u, v, projection=projection, longitude=-25.0, latitude=78.0
        )
        assert len(speed_result) == 2

    def test_select_variables_edge_cases(self):
        """Test _select_variables with edge cases."""
        variables_available = {
            "temp": {"model_variable": ["temperature"]},
            "wind": {"model_variable": ["u_wind", "v_wind"]},
        }

        # Test with empty list
        result = _select_variables([], variables_available)
        assert result == []

        # Test with single variable that maps to multiple model variables
        result = _select_variables(["wind"], variables_available)
        assert set(result) == {"u_wind", "v_wind"}

    def test_update_history_multiple_calls(self):
        """Test update_history with multiple calls to verify history accumulation."""
        import xarray as xr

        ds = xr.Dataset()

        # First update
        ds = update_history(ds, "First operation")
        assert "First operation" in ds.attrs["history"]

        # Second update
        ds = update_history(ds, "Second operation")
        assert "First operation" in ds.attrs["history"]
        assert "Second operation" in ds.attrs["history"]


class TestModelAromeArcticAdditionalCoverage:
    """Additional test cases to improve coverage for ModelAromeArctic class."""

    def test_model_arome_arctic_error_conditions(self):
        """Test ModelAromeArctic error handling and edge cases."""
        from app.api.v3.endpoints.forecast_model.model_aa import ModelAromeArctic

        # Test with coordinates that might cause issues
        model = ModelAromeArctic(longitude=0.0, latitude=78.0, time=datetime.now())
        assert model.x is not None
        assert model.y is not None

        # Test with reasonable coordinates for Svalbard region
        model = ModelAromeArctic(longitude=-15.0, latitude=78.0, time=datetime.now())
        assert model.x is not None
        assert model.y is not None

    def test_model_arome_arctic_variable_validation(self):
        """Test variable selection and validation."""
        from app.api.v3.endpoints.forecast_model.model_aa import ModelAromeArctic
        from app.api.v3.endpoints.forecast_model.model import _select_variables

        # Test selecting all surface variables
        surface_vars = list(ModelAromeArctic.variables_surface.keys())
        result = _select_variables(surface_vars, ModelAromeArctic.variables_surface)
        assert len(result) > 0

        # Test selecting all profile variables
        profile_vars = list(ModelAromeArctic.variables_profile.keys())
        result = _select_variables(profile_vars, ModelAromeArctic.variables_profile)
        assert len(result) > 0


class TestModelAromeArcticConnector:
    """Unit tests for ModelAromeArcticConnector's grid distance check and locking.

    ModelAromeArcticConnector is a process-wide singleton, so tests restore
    whatever `ds_grid`/`ds` was set on it beforehand to avoid bleeding state
    into other tests.
    """

    @pytest.fixture
    def connector(self):
        from app.api.v3.endpoints.forecast_model.model_aa import (
            ModelAromeArcticConnector,
        )

        conn = ModelAromeArcticConnector()
        original_ds_grid = conn.ds_grid
        original_ds = conn.ds
        yield conn
        conn.ds_grid = original_ds_grid
        conn.ds = original_ds

    def test_check_grid_index_distance_tolerance_is_kilometers(self, connector):
        """Regression test: distance is computed in meters and must be
        compared in kilometers against MAX_GRID_DISTANCE_KM (3.6), not
        compared directly against the raw meter value.
        """
        # Two grid points 10 km apart so a query point can be placed clearly
        # inside/outside the 3.6 km tolerance around the nearest one.
        connector.ds_grid = xr.Dataset(
            {"x": ("x", [0.0, 10000.0]), "y": ("y", [0.0, 10000.0])}
        )

        # 3 km from the (0, 0) grid point: within tolerance.
        idx_x, idx_y = connector.check_grid_index(3000.0, 0.0)
        assert (idx_x, idx_y) == (0, 0)

        # 4.2 km from the (0, 0) grid point: outside tolerance.
        with pytest.raises(ValueError, match="3.6 km"):
            connector.check_grid_index(4200.0, 0.0)

    def test_close_does_not_deadlock_when_called_while_lock_held(self, connector):
        """close() is invoked from _check_inactivity(), which always runs
        with the lock already held by the calling thread. Regression test
        for the RLock fix - a plain Lock would deadlock here.
        """
        fake_ds = MagicMock()
        connector.ds = fake_ds

        result = {}

        def worker():
            with connector._lock:
                connector.close()
            result["done"] = True

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=2)

        assert result.get("done") is True, "close() appears to have deadlocked"
        assert connector.ds is None
        fake_ds.close.assert_called_once()
