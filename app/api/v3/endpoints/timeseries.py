from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from app.models.stations_data import StationTimeseries, StationTimeseriesDataPoint
import os
import pandas as pd
import json

router = APIRouter()

# Define path for long term timeseries data
LONG_TIMESERIES_PATH = "./data/000_long_timeseries"

# Define path for stations status data
STATIONS_STATUS_PATH = "./data/000_stations_status/all_dict.json"

# Maximum number of time steps to return
MAX_TIMESTEPS = 200


def get_available_dates_for_station(station_id: str) -> List[str]:
    """Get list of available dates for a specific station"""
    station_path = os.path.join(LONG_TIMESERIES_PATH, station_id)
    try:
        files = [
            f.replace(".parquet", "")
            for f in os.listdir(station_path)
            if f.endswith(".parquet")
        ]
        return sorted(files)
    except FileNotFoundError:
        return []


def load_timeseries_data(station_id: str, date: str) -> Dict[str, Any]:
    """Load timeseries data from parquet file"""
    file_path = os.path.join(LONG_TIMESERIES_PATH, station_id, f"{date}.parquet")

    try:
        # Check if station exists
        if not check_station_exists(station_id):
            raise HTTPException(status_code=404, detail="Station not found")

        df = pd.read_parquet(file_path)

        # Convert DataFrame to list of dictionaries
        timeseries = []
        for index, row in df.iterrows():
            data_point = {
                "timestamp": index.to_pydatetime(),
            }
            for column in df.columns:
                data_point[column] = row.get(column)
            timeseries.append(data_point)

        return {"station_id": station_id, "date": date, "timeseries": timeseries}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Timeseries data file not found")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reading timeseries data: {str(e)}"
        )


def check_station_exists(station_id: str) -> bool:
    """Check if station exists in stations status data"""
    try:
        with open(STATIONS_STATUS_PATH, "r") as file:
            stations_data = json.load(file)
            return station_id in stations_data
    except FileNotFoundError:
        return False
    except json.JSONDecodeError:
        return False
    except Exception:
        return False


@router.get(
    "/available",
    response_model=List[str],
    responses={
        404: {"description": "Long timeseries data directory not found"},
        500: {"description": "Error reading station list"},
    },
)
async def get_stations_where_historical_data_are_available():
    """
    Get list of stations with available long term timeseries data
    """
    try:
        stations = [
            d
            for d in os.listdir(LONG_TIMESERIES_PATH)
            if os.path.isdir(os.path.join(LONG_TIMESERIES_PATH, d))
        ]
    except FileNotFoundError:
        stations = []

    if not stations:
        raise HTTPException(
            status_code=404, detail="No stations with long timeseries data found"
        )

    return stations


@router.get(
    "/{station_id}/variables",
    response_model=List[str],
    responses={
        404: {"description": "Station not found"},
        500: {"description": "Error getting available variables"},
    },
)
async def get_available_variables_for_the_station_historical_observations(
    station_id: str,
):
    """
    Get list of available variables in timeseries data for a specific station
    """
    try:
        # Check if station exists
        if not check_station_exists(station_id):
            raise HTTPException(status_code=404, detail="Station not found")

        # Get available variables from a sample file
        dates = get_available_dates_for_station(station_id)
        if not dates:
            raise HTTPException(
                status_code=404, detail="No variables found in timeseries data"
            )

        # Use the first available date to get a sample of the variables
        sample_date = dates[0]
        file_path = os.path.join(
            LONG_TIMESERIES_PATH, station_id, f"{sample_date}.parquet"
        )
        df = pd.read_parquet(file_path)
        variables = list(df.columns)
        if not variables:
            raise HTTPException(
                status_code=404, detail="No variables found in timeseries data"
            )

        return variables
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting available variables: {str(e)}"
        )


@router.get(
    "/{station_id}/date-range",
    response_model=Dict[str, Any],
    responses={
        404: {"description": "Station not found or no timeseries data available"},
        500: {"description": "Error getting date range"},
    },
)
async def get_available_historical_time_range_for_a_station(station_id: str):
    """
    Get date range for a specific station's timeseries data
    """
    try:
        # Check if station exists
        if not check_station_exists(station_id):
            raise HTTPException(status_code=404, detail="Station not found")

        dates = get_available_dates_for_station(station_id)
        if not dates:
            raise HTTPException(
                status_code=404, detail="No timeseries data available for this station"
            )

        return {
            "station_id": station_id,
            "min_date": min(dates),
            "max_date": max(dates),
            "available_dates": dates,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting date range: {str(e)}"
        )


@router.get(
    "/{station_id}",
    response_model=StationTimeseries,
    responses={
        400: {"description": "Invalid date range or too many timesteps requested"},
        404: {"description": "Station or date range not found"},
        500: {"description": "Error reading timeseries data"},
    },
)
async def get_station_historical_observations(
    station_id: str,
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """
    Get timeseries data for a specific station and date range
    """
    try:
        # Check if station exists
        if not check_station_exists(station_id):
            raise HTTPException(status_code=404, detail="Station not found")

        # Get all available dates for the station
        all_dates = get_available_dates_for_station(station_id)
        if not all_dates:
            raise HTTPException(
                status_code=404, detail="No timeseries data available for this station"
            )

        # Filter dates within the requested range
        filtered_dates = [date for date in all_dates if start_date <= date <= end_date]
        if not filtered_dates:
            raise HTTPException(
                status_code=404,
                detail="No timeseries data available for the requested date range",
            )

        # Load data from all files in the date range
        all_timeseries = []
        for date in filtered_dates:
            file_path = os.path.join(
                LONG_TIMESERIES_PATH, station_id, f"{date}.parquet"
            )
            try:
                df = pd.read_parquet(file_path)

                # Convert DataFrame to list of dictionaries
                for index, row in df.iterrows():
                    data_point = {
                        "timestamp": index.to_pydatetime(),
                    }
                    for column in df.columns:
                        data_point[column] = row.get(column)
                    all_timeseries.append(data_point)
            except FileNotFoundError:
                continue  # Skip missing files
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error reading timeseries data for {date}: {str(e)}",
                )

        # Sort by timestamp
        all_timeseries.sort(key=lambda x: x["timestamp"])

        # Limit to MAX_TIMESTEPS
        if len(all_timeseries) > MAX_TIMESTEPS:
            all_timeseries = all_timeseries[:MAX_TIMESTEPS]

        # Convert to StationTimeseries model
        timeseries_data_points = []
        for point in all_timeseries:
            # Filter out None values to avoid validation issues
            filtered_data = {
                k: v for k, v in point.items() if v is not None and k != "timestamp"
            }
            data_point = StationTimeseriesDataPoint(
                timestamp=point["timestamp"], **filtered_data
            )
            timeseries_data_points.append(data_point)

        return StationTimeseries(
            station_id=station_id, timeseries=timeseries_data_points
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error loading timeseries data range: {str(e)}"
        )
