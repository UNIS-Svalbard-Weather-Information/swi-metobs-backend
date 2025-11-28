from fastapi import APIRouter, HTTPException, Query, Response
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Literal
from pathlib import Path
import os
from app.models.forecast import ForecastResponse

router = APIRouter()

# Base directory where your forecast files are stored
BASE_DIR = Path("./data/forecast")


def get_files_for_variable(
    variable: str,
    models: Optional[List[str]] = None,
    file_type: Literal["cog", "velocity"] = "cog",
    start_hour: int = -24,
    end_hour: int = 24,
) -> List[Dict[str, str]]:
    """
    Returns a list of files (COG or velocity) for the given variable, models, and hour range.
    """
    files = []
    now = datetime.utcnow()

    # Calculate the time range
    start_time = now + timedelta(hours=start_hour)
    end_time = now + timedelta(hours=end_hour)

    # If no models are specified, use all available models
    if models is None:
        models = [d for d in os.listdir(BASE_DIR) if (BASE_DIR / d).is_dir()]

    for model in models:
        model_dir = BASE_DIR / model / file_type
        if not model_dir.exists():
            continue

        for filename in os.listdir(model_dir):
            if file_type == "cog" and filename.startswith(f"cog_{variable}_"):
                try:
                    timestamp_str = filename.split(f"cog_{variable}_")[1].split(".tif")[
                        0
                    ]
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%SZ")
                except (IndexError, ValueError):
                    continue
                if start_time <= timestamp <= end_time:
                    files.append(
                        {
                            "model": model,
                            "file_path": str(model_dir / filename),
                            "timestamp": timestamp_str,
                        }
                    )
            elif (
                file_type == "velocity"
                and f"_{variable}_" in filename
                and filename.endswith(".json.gz")
            ):
                try:
                    timestamp_str = filename.split(f"_{variable}_")[1].split(
                        ".json.gz"
                    )[0]
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%SZ")
                except (IndexError, ValueError):
                    continue
                if start_time <= timestamp <= end_time:
                    files.append(
                        {
                            "model": model,
                            "file_path": str(model_dir / filename),
                            "timestamp": timestamp_str,
                        }
                    )

    return files


@router.get("/forecast/", response_model=ForecastResponse)
async def get_forecast(
    variable: str,
    file_type: Literal["cog", "velocity"] = "cog",
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
    response: Response = None,  # Add Response parameter for headers
):
    """
    Endpoint to get forecast files (COG or velocity) for a specific variable, model, and hour range.
    """
    if not BASE_DIR.exists():
        raise HTTPException(status_code=404, detail="Forecast not available")

    files = get_files_for_variable(variable, model, file_type, start_hour, end_hour)

    if not files:
        raise HTTPException(
            status_code=404,
            detail=f"No {file_type} files found for the given variable, model, and hour range",
        )

    # Set Cache-Control header for 10 minutes
    response.headers["Cache-Control"] = "public, max-age=600"

    return files


@router.get("/forecast/velocity/{model}/{filename}")
async def get_velocity_file(model: str, filename: str, response: Response):
    """
    Endpoint to download a specific velocity file.
    """
    file_path = BASE_DIR / model / "velocity" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Velocity file not found")

    # Set Cache-Control header for 10 minutes
    response.headers["Cache-Control"] = "public, max-age=600"
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return Response(content=file_path.read_bytes(), media_type="application/json")
