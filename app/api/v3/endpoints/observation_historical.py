from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.models.stations import (
    StationTimeseries,
    StationTimeseriesDataPoint,
    StationPosition,
    StationsAvailableHistoricalDates,
    StationDataRequestModel,
    StationIDModel,
)
from app.utils.path import safe_join
from app.utils.error import handle_validation_error
import dask.dataframe as dd
import os
import pandas as pd
import json
from loguru import logger
from pathlib import Path

router = APIRouter()

# Define paths
LONG_TIMESERIES_PATH = Path("./data/000_long_timeseries")
STATIONS_STATUS_PATH = Path("./data/000_stations_status/all_dict.json")

# Constants
MAX_TIMESTEPS = 200


def get_available_dates_for_station(station_id: str) -> List[str]:
    """Get list of available dates for a specific station."""
    station_path = safe_join(LONG_TIMESERIES_PATH, station_id)
    try:
        files = [
            f.replace(".parquet", "")
            for f in os.listdir(station_path)
            if f.endswith(".parquet")
        ]
        return sorted(files)
    except FileNotFoundError:
        logger.error("Station path not found for station_id: {}".format(station_id))
        raise HTTPException(status_code=404, detail="Station not found")


def check_station_exists(station_id: str) -> bool:
    """Check if station exists in stations status data."""
    try:
        with open(STATIONS_STATUS_PATH, "r") as file:
            stations_data = json.load(file)
            return station_id in stations_data
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        logger.error("Error checking station existence: {}".format(str(e)))
        return False


@router.get(
    "/available",
    response_model=List[str],
    responses={
        404: {"description": "Long timeseries data directory not found"},
        500: {"description": "Error reading station list"},
    },
)
async def get_stations_where_historical_data_are_available() -> List[str]:
    """
    Get list of stations with available long term timeseries data.
    """
    try:
        stations = [
            d
            for d in os.listdir(LONG_TIMESERIES_PATH)
            if os.path.isdir(safe_join(LONG_TIMESERIES_PATH, d))
        ]
    except FileNotFoundError:
        logger.error(
            f"Long timeseries data directory not found at path: {LONG_TIMESERIES_PATH}"
        )
        raise HTTPException(
            status_code=404, detail="Long timeseries data directory not found"
        )

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
        404: {"description": "Station not found or no variables found"},
        500: {"description": "Error getting available variables"},
    },
)
async def get_available_variables_for_the_station_historical_observations(
    station_id: str,
) -> List[str]:
    """
    Get list of available variables in timeseries data for a specific station.
    """
    handle_validation_error(StationIDModel, id=station_id)
    try:
        if not check_station_exists(station_id):
            logger.error("Station not found: {}".format(station_id))
            raise HTTPException(status_code=404, detail="Station not found")

        dates = get_available_dates_for_station(station_id)
        if not dates:
            raise HTTPException(
                status_code=404, detail="No variables found in timeseries data"
            )

        sample_date = dates[0]
        file_path = safe_join(
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
        logger.error("Error getting available variables: {}".format(str(e)))
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
    """
    logger.info("ok")
    handle_validation_error(StationIDModel, id=station_id)
    
    try:
        if not check_station_exists(station_id):
            logger.error("Station not found: {}".format(station_id))
            raise HTTPException(status_code=404, detail="Station not found")

        dates = get_available_dates_for_station(station_id)
        if not dates:
            raise HTTPException(
                status_code=404,
                detail="No timeseries data available for this station",
            )

        return StationsAvailableHistoricalDates(
            id=station_id,
            min_date=min(dates),
            max_date=max(dates),
            available_dates=dates,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting date range: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Internal server error when getting the available time range",
        )


@router.get("/{station_id}", response_model=StationTimeseries)
async def get_station_historical_observations(
    station_id: str,
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    variables: Optional[List[str]] = Query(
        None, description="List of variables to include"
    ),
    resample: bool = Query(
        False, description="Enable resampling if data exceeds limit"
    ),
) -> StationTimeseries:
    """
    Get the historical time serie data for a given station.
    """
    # Validate input using your Pydantic model
    handle_validation_error(
        StationDataRequestModel,
        id=station_id,
        start_date=start_date,
        end_date=end_date,
        variables=variables,
        resample=resample,
    )

    try:
        if not check_station_exists(station_id):
            logger.error("Station not found: {}".format(station_id))
            raise HTTPException(
                status_code=404, detail=f"Station {station_id} not found"
            )

        all_dates = get_available_dates_for_station(station_id)
        if not all_dates:
            raise HTTPException(
                status_code=404,
                detail=f"Historical data not available for station {station_id}",
            )

        filtered_dates = [date for date in all_dates if start_date <= date <= end_date]
        if not filtered_dates:
            raise HTTPException(
                status_code=404,
                detail=f"No historical data available for the station {station_id} in the date range {start_date} to {end_date}.",
            )

        parquet_files = [
            safe_join(LONG_TIMESERIES_PATH, station_id, f"{date}.parquet")
            for date in filtered_dates
        ]

        ddf = dd.read_parquet(parquet_files)
        if variables:
            variables_availables = [var for var in variables if var in ddf.columns]
            if "latitude" in ddf.columns and "longitude" in ddf.columns:
                variables_availables.extend(["latitude", "longitude"])
            ddf = ddf[variables_availables]
        ddf = ddf.loc[start_date:end_date]

        index = ddf.index.compute()

        if len(index) > MAX_TIMESTEPS and not resample:
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

        timeseries = []
        for index, row in df.iterrows():
            data_point = {}
            if "latitude" in df.columns and "longitude" in df.columns:
                data_point["location"] = StationPosition(
                    lat=row.get("latitude"), lon=row.get("longitude")
                )
            for column in df.columns:
                if column not in ["latitude", "longitude"]:
                    data_point[column] = row.get(column)
            timeseries.append(
                StationTimeseriesDataPoint(
                    timestamp=index.to_pydatetime(), **data_point
                )
            )
        return StationTimeseries(id=station_id, timeseries=timeseries)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error loading timeseries data: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Server error loading timeseries data range",
        )
