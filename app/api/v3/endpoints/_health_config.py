from pathlib import Path

# Centralized configuration for health check paths
# This makes it easy to maintain and update when new data paths are added

HEALTH_CHECK_PATHS = {
    # Station status files
    "stations_status": Path("./data/realtime/000_stations_status/all_dict.json"),
    "online_stations": Path("./data/realtime/000_stations_status/online_dict.json"),
    "offline_stations": Path("./data/realtime/000_stations_status/offline_dict.json"),
    # Observation data
    "latest_observations": Path("./data/realtime/000_latest_obs/latest_dict.json"),
    "long_timeseries_dir": Path("./data/historical/000_long_timeseries"),
    # Forecast data
    "forecast_dir": Path("./data/forecast"),
    # Hourly data (if used)
    "hourly_data_template": Path("./data/realtime/000_hourly_data/{offset}.json"),
}

# Paths that are critical for basic functionality
CRITICAL_PATHS = [
    "stations_status",
    "online_stations",
    "latest_observations",
    "long_timeseries_dir",
    "forecast_dir",
]

# Paths that are important but not critical
OPTIONAL_PATHS = ["offline_stations", "hourly_data_template"]
