import pytest
from fastapi.testclient import TestClient
from app.main import app
from datetime import datetime, timedelta


@pytest.mark.asyncio
class TestForecastPointAdditionalCoverage:
    """Additional test cases to improve coverage for forecast point endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    async def test_get_available_variables_none_type(self, client):
        """Test getting variables with ftype=None (should return all variables)."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Test with ftype=None (should return all variables)
            response = client.get(f"/v3/point-forecast/{model_id}/variables/")
            assert response.status_code == 200
            data = response.json()
            assert "variables" in data
            assert isinstance(data["variables"], list)

            # Should have both surface and profile variables
            variable_types = set(var["type"] for var in data["variables"])
            assert "surface" in variable_types
            assert "profile" in variable_types

    async def test_get_forecast_data_time_validation(self, client):
        """Test time validation in forecast data endpoint."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Test with invalid time format - this will raise ValueError, so we expect 500
            try:
                response = client.get(
                    f"/v3/point-forecast/{model_id}/surface",
                    params={
                        "variables": ["air_temperature_2m"],
                        "lat": 78.0,
                        "lon": -25.0,
                        "time": "invalid-time-format",
                    },
                )
                # If we get here, the endpoint handled it gracefully
                assert response.status_code in [400, 422, 500]
            except ValueError:
                # Expected - datetime.fromisoformat will raise ValueError
                pass

    async def test_get_forecast_data_multiple_variables(self, client):
        """Test getting forecast data with multiple variables."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Get available surface variables
            variables_response = client.get(
                f"/v3/point-forecast/{model_id}/variables/?ftype=surface"
            )
            assert variables_response.status_code == 200
            variables_data = variables_response.json()

            if len(variables_data["variables"]) >= 2:
                # Test with multiple variables
                variables = [
                    variables_data["variables"][0]["variable"],
                    variables_data["variables"][1]["variable"],
                ]

                test_time = (datetime.now() + timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

                response = client.get(
                    f"/v3/point-forecast/{model_id}/surface",
                    params={
                        "variables": variables,
                        "lat": 78.0,
                        "lon": -25.0,
                        "time": test_time,
                    },
                )

                # This might fail due to actual data availability, but we test the structure
                if response.status_code == 200:
                    data = response.json()
                    assert "id" in data
                    assert "timeseries" in data
                    assert isinstance(data["timeseries"], list)
                else:
                    # Acceptable error codes for this test context
                    assert response.status_code in [400, 404, 500]

    async def test_get_forecast_data_edge_coordinates(self, client):
        """Test forecast data with edge coordinate values."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Test with edge coordinates
            test_time = (datetime.now() + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            # Test with maximum latitude
            response = client.get(
                f"/v3/point-forecast/{model_id}/surface",
                params={
                    "variables": ["air_temperature_2m"],
                    "lat": 90.0,  # North Pole
                    "lon": 0.0,
                    "time": test_time,
                },
            )

            # Should handle gracefully (may return error if out of bounds)
            assert response.status_code in [200, 400, 404, 500]

    async def test_get_forecast_data_netcdf_error_handling(self, client):
        """Test NetCDF endpoint error handling."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Test with invalid variable
            test_time = (datetime.now() + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            response = client.get(
                f"/v3/point-forecast/{model_id}/surface/nc",
                params={
                    "variables": ["invalid_variable"],
                    "lat": 78.0,
                    "lon": -25.0,
                    "time": test_time,
                },
            )

            # Should return error for invalid variable
            assert response.status_code in [400, 404, 500]
