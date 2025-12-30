from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.models.stations_data import StationTimeseries
import os
import json

router = APIRouter()

# Define paths as variables
LATEST_DATA_PATH = "./data/000_latest_obs/latest_dict.json"
HOURLY_DATA_PATH = "./data/000_hourly_data/{offset}.json"

# Environment variable to enable forecast data
enable_forecast = (
    os.getenv("SWI_METOBS_BACKEND_ENABLE_FORECAST_OBSERVATION", "false").lower()
    == "true"
)


def load_data(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON data")


@router.get(
    "/stations/{station_id}",
    response_model=StationTimeseries,
    responses={
        400: {"description": "Offset out of range or forecast data not enabled"},
        404: {"description": "Data file not found or station not found"},
        500: {"description": "Invalid JSON data"},
    },
)
async def get_station_observations(station_id: str, offset: int = 0):
    """
    Get data for a specific station with optional time offset.
    - offset: 0 for latest data, negative for past data, positive for forecast data.
    """
    # Validate the offset
    if offset < -24 or offset > 24:
        raise HTTPException(
            status_code=400, detail="Offset out of range. Must be between -24 and 24."
        )

    # Determine if we are asking for forecast data
    if offset > 0 and not enable_forecast:
        raise HTTPException(status_code=400, detail="Forecast data is not enabled")

    # Determine the file to read based on the offset
    if offset == 0:
        file_path = LATEST_DATA_PATH
    else:
        file_path = HOURLY_DATA_PATH.format(offset=offset)

    # Load the data from the file
    data = load_data(file_path)

    # Check if the station_id exists in the data
    if station_id not in data:
        raise HTTPException(status_code=404, detail="Station not found")

    # Extract the relevant station data
    station_data = data[station_id]

    # Create the response model
    return StationTimeseries(
        station_id=station_id, timeseries=station_data.get("timeseries", [])
    )


@router.get(
    "/stations",
    response_model=List[StationTimeseries],
    responses={
        400: {"description": "Offset out of range or forecast data not enabled"},
        404: {"description": "Data file not found"},
        500: {"description": "Invalid JSON data"},
    },
)
async def get_all_stations_observations(offset: int = 0):
    """
    Get data for all stations with optional time offset.
    - offset: 0 for latest data, negative for past data, positive for forecast data.
    """
    # Validate the offset
    if offset < -24 or offset > 24:
        raise HTTPException(
            status_code=400, detail="Offset out of range. Must be between -24 and 24."
        )

    # Determine if we are asking for forecast data
    if offset > 0 and not enable_forecast:
        raise HTTPException(status_code=400, detail="Forecast data is not enabled")

    # Determine the file to read based on the offset
    if offset == 0:
        file_path = LATEST_DATA_PATH
    else:
        file_path = HOURLY_DATA_PATH.format(offset=offset)

    # Load the data from the file
    data = load_data(file_path)

    # Format the response
    stations = []
    for station_id, station_data in data.items():
        stations.append(
            StationTimeseries(
                station_id=station_id, timeseries=station_data.get("timeseries", [])
            )
        )

    return stations
