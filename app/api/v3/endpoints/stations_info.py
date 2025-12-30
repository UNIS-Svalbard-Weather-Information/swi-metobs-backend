from fastapi import HTTPException, APIRouter
import json
from pathlib import Path
from app.models.stations_data import StationMetadata, StationIDModel
from app.utils.error import handle_validation_error

# Get the router from parent
router = APIRouter()

# Path to the JSON files
STATIONS_FILE = Path("./data/000_stations_status/all_dict.json")
ONLINE_STATIONS_FILE = Path("./data/000_stations_status/online_dict.json")
OFFLINE_STATIONS_FILE = Path("./data/000_stations_status/offline_dict.json")


@router.get("/online", response_model=dict[str, StationMetadata])
async def get_online_stations():
    """Get information for online stations"""
    try:
        with open(ONLINE_STATIONS_FILE) as f:
            stations = json.load(f)
        return stations
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="The service is temporarily unavailable. Please try again later.",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your request.",
        )


@router.get("/offline", response_model=dict[str, StationMetadata])
async def get_offline_stations():
    """Get information for offline stations"""
    try:
        with open(OFFLINE_STATIONS_FILE) as f:
            stations = json.load(f)
        return stations
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="The service is temporarily unavailable. Please try again later.",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your request.",
        )


@router.get("/", response_model=dict[str, StationMetadata])
async def get_all_stations():
    """Get information for all stations"""
    try:
        with open(STATIONS_FILE) as f:
            stations = json.load(f)
        return stations
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="The service is temporarily unavailable. Please try again later.",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your request.",
        )


@router.get("/{station_id}", response_model=StationMetadata)
async def get_station(station_id: str):
    """Get information for a specific station"""

    handle_validation_error(StationIDModel, id=station_id)

    try:
        with open(STATIONS_FILE) as f:
            stations = json.load(f)

        if station_id not in stations:
            raise HTTPException(
                status_code=404, detail=f"Station {station_id} not found"
            )

        return stations[station_id]
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="The service is temporarily unavailable. Please try again later.",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your request.",
        )
