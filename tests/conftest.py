import pytest
from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path
import os
import json
from datetime import datetime
import pandas as pd


@pytest.fixture(scope="session")
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_test_data():
    """Set up test data directories and files."""
    import shutil

    # Check if data directory exists and rename it temporarily
    test_data_backup = None
    if os.path.exists("./data"):
        test_data_backup = "./_data_backup"
        shutil.move("./data", test_data_backup)

    # Create necessary directories
    os.makedirs("./data/000_long_timeseries", exist_ok=True)
    os.makedirs("./data/000_stations_status", exist_ok=True)
    os.makedirs("./data/000_latest_obs", exist_ok=True)
    os.makedirs("./data/forecast", exist_ok=True)

    # Create test station data
    test_station_id = "TEST001"
    station_dir = Path(f"./data/000_long_timeseries/{test_station_id}")
    station_dir.mkdir(exist_ok=True)

    # Create a simple parquet file for testing
    test_data = pd.DataFrame(
        {
            "timestamp": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
            "temperature": [10.5, 12.3],
            "humidity": [65.2, 70.1],
        }
    )
    test_data.set_index("timestamp", inplace=True)
    test_data.to_parquet(station_dir / "2023-01-01.parquet")

    # Create stations status JSON
    stations_data = {
        test_station_id: {
            "id": test_station_id,
            "name": "Test Station",
            "type": "fixed",
            "location": {"lat": 45.0, "lon": 6.0},
            "variables": ["temperature", "humidity"],
            "status": "online",
            "last_updated": datetime.now().isoformat(),
            "project": "test",
            "icon": "test-icon",
        }
    }

    with open("./data/000_stations_status/all_dict.json", "w") as f:
        json.dump(stations_data, f)

    with open("./data/000_stations_status/online_dict.json", "w") as f:
        json.dump({test_station_id: stations_data[test_station_id]}, f)

    with open("./data/000_stations_status/offline_dict.json", "w") as f:
        json.dump({}, f)

    # Create latest observations data
    latest_data = {
        test_station_id: {
            "timeseries": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "temperature": 15.0,
                    "humidity": 68.5,
                }
            ]
        }
    }

    with open("./data/000_latest_obs/latest_dict.json", "w") as f:
        json.dump(latest_data, f)

    # Create forecast directory structure
    forecast_model_dir = Path("./data/forecast/test_model/cog")
    forecast_model_dir.mkdir(parents=True, exist_ok=True)

    # Create a test forecast file
    forecast_file = forecast_model_dir / "cog_temperature_2023-01-01T000000Z.tif"
    forecast_file.touch()

    yield

    # Cleanup - remove test data and restore original if it existed
    import shutil

    shutil.rmtree("./data", ignore_errors=True)

    if test_data_backup and os.path.exists(test_data_backup):
        shutil.move(test_data_backup, "./data")
