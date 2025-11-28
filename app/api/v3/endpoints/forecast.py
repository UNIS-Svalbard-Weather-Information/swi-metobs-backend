from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import os

from app.models.forecast import ForecastResponse

router = APIRouter()

# Base directory where your forecast files are stored
BASE_DIR = Path("./data/forecast")


def get_files_for_variable(
    variable: str,
    models: Optional[List[str]] = None,
    start_hour: int = -24,
    end_hour: int = 24,
) -> List[Dict[str, str]]:
    """
    Returns a list of files for the given variable, models, and hour range.
    """
    files = []
    now = datetime.utcnow()

    # Calculate the time range
    start_time = now + timedelta(hours=start_hour)
    end_time = now + timedelta(hours=end_hour)

    # If no models are specified, use all available models
    if models is None:
        models = [
            d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))
        ]

    for model in models:
        model_dir = os.path.join(BASE_DIR, model, "cog")
        if not os.path.exists(model_dir):
            continue

        for filename in os.listdir(model_dir):
            if filename.startswith(f"cog_{variable}_"):
                try:
                    # Extract timestamp from filename
                    timestamp_str = filename.split(f"cog_{variable}_")[1].split(".tif")[
                        0
                    ]
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%SZ")
                except (IndexError, ValueError):
                    continue

                # Check if the timestamp is within the specified range
                if start_time <= timestamp <= end_time:
                    files.append(
                        {
                            "model": model,
                            "file_path": os.path.join(model_dir, filename),
                            "timestamp": timestamp_str,
                        }
                    )

    return files


@router.get("/forecast/", response_model=ForecastResponse)
async def get_forecast(
    variable: str,
    model: Optional[List[str]] = Query(
        None,
        description="List of models to filter by (e.g., aa, bb). If not provided, all models are returned.",
    ),
    start_hour: int = Query(
        -24, description="Start hour offset from now (e.g., -24 for 24 hours ago)"
    ),
    end_hour: int = Query(
        24, description="End hour offset from now (e.g., 24 for 24 hours ahead)"
    ),
):
    """
    Endpoint to get forecast files for a specific variable, model, and hour range.
    """
    if not os.path.exists(BASE_DIR):
        raise HTTPException(status_code=404, detail="Forecast not available")

    files = get_files_for_variable(variable, model, start_hour, end_hour)

    if not files:
        raise HTTPException(
            status_code=404,
            detail="No files found for the given variable, model, and hour range",
        )

    return files
