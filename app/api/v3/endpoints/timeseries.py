from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Dict, Any, Optional
from app.models.stations_data import (
    StationTimeseries,
    StationTimeseriesDataPoint,
    StationPosition,
    StationsAvailableHistoricalDates,
)
import dask.dataframe as dd
from dask.diagnostics import ProgressBar
import os
import pandas as pd
import json
from loguru import logger
from datetime import datetime

router = APIRouter()

# Define path for long term timeseries data
LONG_TIMESERIES_PATH = "./data/000_long_timeseries"

# Define path for stations status data
STATIONS_STATUS_PATH = "./data/000_stations_status/all_dict.json"

# Maximum number of time steps to return
MAX_TIMESTEPS = 200


def get_available_dates_for_station(station_id: str) -> List[str]:
    """Get list of available dates for a specific station.

    Args:
        station_id (str): The ID of the station.

    Returns:
        List[str]: A sorted list of available dates for the station.
    """
    station_path = os.path.join(LONG_TIMESERIES_PATH, station_id)
    try:
        files = [
            f.replace(".parquet", "")
            for f in os.listdir(station_path)
            if f.endswith(".parquet")
        ]
        return sorted(files)
    except FileNotFoundError:
        logger.error(f"Station path not found for station_id: {station_id}")
        return []


def load_timeseries_data(station_id: str, date: str) -> Dict[str, Any]:
    """Load timeseries data from parquet file.

    Args:
        station_id (str): The ID of the station.
        date (str): The date for which to load the timeseries data.

    Returns:
        Dict[str, Any]: A dictionary containing the station ID, date, and timeseries data.

    Raises:
        HTTPException: 404 if the station is not found or the timeseries data file is not found.
        HTTPException: 500 if there is an error reading the timeseries data.
    """
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
        logger.error(
            f"Timeseries data file not found for station_id: {station_id} and date: {date}"
        )
        raise HTTPException(status_code=404, detail="Timeseries data file not found")
    except Exception as e:
        logger.error(
            f"Error reading timeseries data for station_id: {station_id} and date: {date}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail="Error reading timeseries data")


def check_station_exists(station_id: str) -> bool:
    """Check if station exists in stations status data.

    Args:
        station_id (str): The ID of the station.

    Returns:
        bool: True if the station exists, False otherwise.
    """
    try:
        with open(STATIONS_STATUS_PATH, "r") as file:
            stations_data = json.load(file)
            return station_id in stations_data
    except FileNotFoundError:
        logger.error(f"Stations status file not found at path: {STATIONS_STATUS_PATH}")
        return False
    except json.JSONDecodeError:
        logger.error(
            f"Error decoding JSON from stations status file at path: {STATIONS_STATUS_PATH}"
        )
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking station existence: {str(e)}")
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
    Get list of stations with available long term timeseries data.

    Returns:
        List[str]: A list of station IDs with available long-term timeseries data.

    Raises:
        HTTPException: 404 if no stations with long timeseries data are found.
    """
    try:
        stations = [
            d
            for d in os.listdir(LONG_TIMESERIES_PATH)
            if os.path.isdir(os.path.join(LONG_TIMESERIES_PATH, d))
        ]
    except FileNotFoundError:
        logger.error(
            f"Long timeseries data directory not found at path: {LONG_TIMESERIES_PATH}"
        )
        stations = []

    if not stations:
        logger.error("No stations with long timeseries data found")
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
    Get list of available variables in timeseries data for a specific station.

    Args:
        station_id (str): The ID of the station.

    Returns:
        List[str]: A list of available variables for the station.

    Raises:
        HTTPException: 404 if the station is not found or no variables are found.
        HTTPException: 500 if there is an error getting available variables.
    """
    try:
        # Check if station exists
        if not check_station_exists(station_id):
            logger.error(f"Station not found: {station_id}")
            raise HTTPException(status_code=404, detail="Station not found")

        # Get available variables from a sample file
        dates = get_available_dates_for_station(station_id)
        if not dates:
            logger.error(
                f"No variables found in timeseries data for station_id: {station_id}"
            )
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
            logger.error(
                f"No variables found in timeseries data for station_id: {station_id}"
            )
            raise HTTPException(
                status_code=404, detail="No variables found in timeseries data"
            )

        return variables
    except Exception as e:
        logger.error(
            f"Error getting available variables for station_id: {station_id}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail="Error getting available variables")


@router.get(
    "/{station_id}/date-range",
    response_model=StationsAvailableHistoricalDates,
    responses={
        404: {"description": "Station not found or no timeseries data available"},
        500: {"description": "Internal server error"},
    },
)
async def get_available_historical_time_range_for_a_station(
    station_id: str,
) -> StationsAvailableHistoricalDates:
    """
    Get the available date range for a specific station's timeseries data.

    Args:
        station_id (str): The ID of the station.

    Returns:
        StationsAvailableHistoricalDates: An object containing the min, max, and all available dates.

    Raises:
        HTTPException: 404 if the station is not found or has no data, 500 for internal errors.
    """
    try:
        # Check if station exists
        if not check_station_exists(station_id):
            logger.error(f"Station not found: {station_id}")
            raise HTTPException(
                status_code=404, detail="Station not found"
            )

        dates = get_available_dates_for_station(station_id)
        if not dates:
            logger.error(f"No timeseries data available for station_id: {station_id}")
            raise HTTPException(
                status_code=404,
                detail="No timeseries data available for this station",
            )

        return StationsAvailableHistoricalDates(
            station_id=station_id,
            min_date=min(dates),
            max_date=max(dates),
            available_dates=dates,
        )

    except Exception as e:
        logger.error(
            f"Internal server error when getting the available time range for station_id: {station_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error when getting the available time range",
        )


@router.get("/{station_id}", response_model=StationTimeseries)
async def get_station_historical_observations(
    station_id: str,
    start_date: str = Query(..., description="Start date in YYYY-%m-%d format"),
    end_date: str = Query(..., description="End date in YYYY-%m-%d format"),
    variables: Optional[List[str]] = Query(
        None, description="List of variables to fetch"
    ),
    resample: bool = Query(
        False,
        description="Flag to enable resampling of observations if exceeding max timesteps",
    ),
):
    """
    Get the historical time serie data for a given station.

    Args:
        station_id (str): The ID of the station.
        start_date (str): The start date in YYYY-%m-%d format.
        end_date (str): The end date in YYYY-%m-%d format.
        variables (Optional[List[str]]): List of variables to fetch.
        resample (bool): Flag to enable resampling of observations if exceeding max timesteps.

    Returns:
        StationTimeseries: The historical timeseries data for the station.

    Raises:
        HTTPException: 404 if the station is not found or no data is available in the date range.
        HTTPException: 400 if the requested data exceeds the maximum allowed timesteps.
        HTTPException: 500 if there is an error loading the timeseries data range.
    """
    try:
        # Check if station exists
        if not check_station_exists(station_id):
            logger.error(f"Station not found: {station_id}")
            raise HTTPException(
                status_code=404, detail=f"Station {station_id} not found"
            )

        # Get all available dates for the station
        all_dates = get_available_dates_for_station(station_id)
        if not all_dates:
            logger.error(f"Historical data not available for station_id: {station_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Historical data not available for station {station_id}",
            )

        # Filter dates within the requested range
        filtered_dates = [date for date in all_dates if start_date <= date <= end_date]
        if not filtered_dates:
            logger.error(
                f"No historical data available for station_id: {station_id} in the date range {start_date} to {end_date}"
            )
            raise HTTPException(
                status_code=404,
                detail=f"Historical data not available for the station {station_id} in the date range {start_date} to {end_date}.",
            )

        # Build the list of Parquet files to read
        parquet_files = [
            os.path.join(LONG_TIMESERIES_PATH, station_id, f"{date}.parquet")
            for date in filtered_dates
        ]

        # Use Dask to read all Parquet files and filter by date range and variables
        ddf = dd.read_parquet(parquet_files)
        if variables:
            variables_availables = [var for var in variables if var in ddf.columns]
            if "latitude" in ddf.columns and "longitude" in ddf.columns:
                variables_availables.extend(["latitude", "longitude"])
            ddf = ddf[variables_availables]
        ddf = ddf.loc[start_date:end_date]

        # Compute the Dask DataFrame to a Pandas DataFrame
        index = ddf.index.compute()

        if len(index) > MAX_TIMESTEPS and not resample:
            logger.error(
                f"Requested data exceeds maximum allowed timesteps ({MAX_TIMESTEPS}) for station_id: {station_id}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Requested data exceeds maximum allowed timesteps ({MAX_TIMESTEPS}). Please narrow the date range or enable resampling.",
            )
        elif len(index) > MAX_TIMESTEPS and resample:
            total_minutes = (index.max() - index.min()).total_seconds() / 60
            interval_minutes = total_minutes / MAX_TIMESTEPS
            resample_interval = int(interval_minutes // 10) * 10
            ddf = ddf.resample(f"{resample_interval}min").mean()

        df = ddf.compute()

        # Convert DataFrame to list of StationTimeseriesDataPoint
        timeseries = []
        for index, row in df.iterrows():
            data_point = {}

            # Check if 'latitude' and 'longitude' are in the columns
            if "latitude" in df.columns and "longitude" in df.columns:
                data_point["location"] = StationPosition(
                    lat=row.get("latitude"), lon=row.get("longitude")
                )

            # Add the other variables
            for column in df.columns:
                if column not in [
                    "latitude",
                    "longitude",
                ]:  # Skip as already added to 'location'
                    data_point[column] = row.get(column)

            timeseries.append(
                StationTimeseriesDataPoint(
                    timestamp=index.to_pydatetime(), **data_point
                )
            )
        return StationTimeseries(station_id=station_id, timeseries=timeseries)

    except HTTPException:
        # Re-raise HTTP exceptions to avoid catching them here
        raise
    except Exception as e:
        logger.error(
            f"Error loading timeseries data range for station_id: {station_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail="Serveur error loading timeseries data range",
        )