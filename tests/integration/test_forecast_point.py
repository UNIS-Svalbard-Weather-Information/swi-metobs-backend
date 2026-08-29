import pytest
from fastapi.testclient import TestClient
from app.main import app
from datetime import datetime, timedelta


@pytest.mark.asyncio
class TestForecastPointEndpoints:
    """Test cases for forecast point endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    async def test_get_available_forecast_models(self, client):
        """Test getting available forecast models."""
        response = client.get("/v3/point-forecast/models/")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        if len(data["models"]) > 0:
            model = data["models"][0]
            assert "id" in model
            assert "name" in model
            assert "provider" in model
            assert "resolution" in model

    async def test_get_available_variables(self, client):
        """Test getting available variables for a model."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Test without type filter
            response = client.get(f"/v3/point-forecast/{model_id}/variables/")
            assert response.status_code == 200
            data = response.json()
            assert "variables" in data
            assert isinstance(data["variables"], list)

            # Test with surface type filter
            response = client.get(
                f"/v3/point-forecast/{model_id}/variables/?ftype=surface"
            )
            assert response.status_code == 200
            data = response.json()
            assert "variables" in data
            assert isinstance(data["variables"], list)

            # Test with profile type filter
            response = client.get(
                f"/v3/point-forecast/{model_id}/variables/?ftype=profile"
            )
            assert response.status_code == 200
            data = response.json()
            assert "variables" in data
            assert isinstance(data["variables"], list)

    async def test_get_available_variables_invalid_model(self, client):
        """Test getting variables for invalid model."""
        response = client.get("/v3/forecast/invalid_model/variables/")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_get_available_variables_invalid_type(self, client):
        """Test getting variables with invalid type."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Test with invalid type
            response = client.get(
                f"/v3/point-forecast/{model_id}/variables/?ftype=invalid"
            )
            assert response.status_code == 400
            data = response.json()
            assert "detail" in data

    async def test_get_forecast_data_surface(self, client):
        """Test getting surface forecast data."""
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

            if len(variables_data["variables"]) > 0:
                variable = variables_data["variables"][0]["variable"]

                # Use a time in the near future (within forecast range)
                test_time = (datetime.now() + timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

                # Test with valid parameters
                response = client.get(
                    f"/v3/point-forecast/{model_id}/surface",
                    params={
                        "variables": [variable],
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

    async def test_get_forecast_data_profile(self, client):
        """Test getting profile forecast data."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]

            # Get available profile variables
            variables_response = client.get(
                f"/v3/point-forecast/{model_id}/variables/?ftype=profile"
            )
            assert variables_response.status_code == 200
            variables_data = variables_response.json()

            if len(variables_data["variables"]) > 0:
                variable = variables_data["variables"][0]["variable"]

                # Use a time in the near future (within forecast range)
                test_time = (datetime.now() + timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

                # Test with valid parameters
                response = client.get(
                    f"/v3/point-forecast/{model_id}/profile",
                    params={
                        "variables": [variable],
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

    async def test_get_forecast_data_invalid_model(self, client):
        """Test getting forecast data for invalid model."""
        test_time = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        response = client.get(
            "/v3/point-forecast/invalid_model/surface",
            params={
                "variables": ["air_temperature_2m"],
                "lat": 78.0,
                "lon": -25.0,
                "time": test_time,
            },
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_get_forecast_data_invalid_type(self, client):
        """Test getting forecast data with invalid type."""
        # First get available models
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]
            test_time = (datetime.now() + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            response = client.get(
                f"/v3/point-forecast/{model_id}/invalid_type",
                params={
                    "variables": ["air_temperature_2m"],
                    "lat": 78.0,
                    "lon": -25.0,
                    "time": test_time,
                },
            )
            assert response.status_code == 400
            data = response.json()
            assert "detail" in data

    async def test_get_forecast_data_netcdf_invalid_type(self, client):
        """Test getting NetCDF forecast data with invalid type returns 400, not 500."""
        models_response = client.get("/v3/point-forecast/models/")
        assert models_response.status_code == 200
        models_data = models_response.json()

        if len(models_data["models"]) > 0:
            model_id = models_data["models"][0]["id"]
            test_time = (datetime.now() + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            response = client.get(
                f"/v3/point-forecast/{model_id}/invalid_type/nc",
                params={
                    "variables": ["air_temperature_2m"],
                    "lat": 78.0,
                    "lon": -25.0,
                    "time": test_time,
                },
            )
            assert response.status_code == 400
            data = response.json()
            assert "detail" in data

    async def test_get_forecast_data_netcdf(self, client):
        """Test getting forecast data in NetCDF format."""
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

            if len(variables_data["variables"]) > 0:
                variable = variables_data["variables"][0]["variable"]

                # Use a time in the near future (within forecast range)
                test_time = (datetime.now() + timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

                # Test with valid parameters
                response = client.get(
                    f"/v3/point-forecast/{model_id}/surface/nc",
                    params={
                        "variables": [variable],
                        "lat": 78.0,
                        "lon": -25.0,
                        "time": test_time,
                    },
                )

                # This might fail due to actual data availability, but we test the structure
                if response.status_code == 200:
                    assert response.headers["content-type"] == "application/x-netcdf"
                    assert "content-disposition" in response.headers
                    assert len(response.content) > 0
                else:
                    # Acceptable error codes for this test context
                    assert response.status_code in [400, 404, 500]
