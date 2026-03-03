from fastapi import APIRouter, HTTPException, Query, Response, Request
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Literal
from pathlib import Path
import os
from app.models.forecast import (
    ForecastResponse,
    ForecastRequestModel,
    ForecastFile,
    AvailableVariablesResponse,
)
from app.utils.error import handle_validation_error
from app.utils.cache import cache_response
from loguru import logger
from app.utils.path import safe_join

router = APIRouter()

# Base directory where your forecast files are stored
BASE_DIR = Path("./data/forecast")


def get_available_variables() -> List[Dict[str, str]]:
    """
    Returns a list of available variables with their type and model.
    """
    variables = []

    # If forecast directory doesn't exist, return empty list
    if not BASE_DIR.exists():
        return variables

    # Get all models
    models = [d for d in os.listdir(BASE_DIR) if (BASE_DIR / d).is_dir()]

    for model in models:
        # Check COG variables
        cog_dir = safe_join(BASE_DIR, model, "cog", relative=True)
        if cog_dir.exists():
            cog_files = os.listdir(cog_dir)
            cog_vars = set()
            for filename in cog_files:
                if filename.startswith("cog_") and filename.endswith(".tif"):
                    # Extract variable name between "cog_" and timestamp
                    parts = filename.split("cog_")[1].split("_")
                    if len(parts) >= 2:
                        # Variable name is everything before the timestamp
                        var_parts = parts[:-1]
                        variable = "_".join(var_parts)
                        cog_vars.add(variable)

            for variable in cog_vars:
                variables.append({"variable": variable, "type": "cog", "model": model})

        # Check velocity variables
        velocity_dir = safe_join(BASE_DIR, model, "velocity", relative=True)
        if velocity_dir.exists():
            velocity_files = os.listdir(velocity_dir)
            velocity_vars = set()
            for filename in velocity_files:
                if filename.startswith("leaflet_velocity_") and filename.endswith(
                    ".json.gz"
                ):
                    # Extract variable name between "leaflet_velocity_" and timestamp
                    parts = filename.split("leaflet_velocity_")[1].split("_")
                    if len(parts) >= 2:
                        # Variable name is everything before the timestamp
                        var_parts = parts[:-1]
                        variable = "_".join(var_parts)
                        velocity_vars.add(variable)

            for variable in velocity_vars:
                variables.append(
                    {"variable": variable, "type": "velocity", "model": model}
                )

    return variables


def get_files_for_variable(
    request: Request,
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
        model_dir = safe_join(BASE_DIR, model, file_type, relative=True)
        # model_dir = BASE_DIR / model / file_type
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
                        ForecastFile(
                            model=model,
                            file_path=str(model_dir / filename),
                            timestamp=timestamp_str,
                        )
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
                        ForecastFile(
                            model=model,
                            file_path=str(
                                request.url_for(
                                    "get_leaflet_velocity_file",
                                    model=model,
                                    filename=filename,
                                )
                            ),
                            # file_path=str(filename),
                            timestamp=timestamp_str,
                        )
                    )

    return files


@router.get("/available/", response_model=AvailableVariablesResponse)
@cache_response(ttl=3600)  # Cache for 1 hour
async def get_available_variables_endpoint():
    """
    Endpoint to get the list of available variables with their associated type and model.
    """
    if not BASE_DIR.exists():
        logger.error("Forecast directory {} not available.".format(BASE_DIR))
        raise HTTPException(status_code=404, detail="Forecast not available")

    variables = get_available_variables()

    if not variables:
        raise HTTPException(
            status_code=404,
            detail="No variables found in the forecast directory",
        )

    return AvailableVariablesResponse(variables=variables)


@router.get("/list/", response_model=ForecastResponse)
@cache_response(ttl=600)
async def get_available_forecast(
    variable: str,
    file_type: Literal["cog", "velocity"] = "cog",
    model: Optional[List[str]] = Query(
        None,
        description="List of models to filter by (aa = Arome Arctic). If not provided, all models are returned.",
    ),
    start_hour: int = Query(
        -24, description="Start hour offset from now (e.g., -24 for 24 hours ago)"
    ),
    end_hour: int = Query(
        24, description="End hour offset from now (e.g., 24 for 24 hours ahead)"
    ),
    response: Response = None,  # Add Response parameter for headers
    request: Request = None,  # Add Request parameter if needed for URL generation
):
    """
    Endpoint to get forecast files (COG or velocity) for a specific variable, model, and hour range. The filepath for velocity files is a URL to the download endpoint and for COG the path to the file to use in Titiler.
    """
    # Validate input using your Pydantic model
    handle_validation_error(
        ForecastRequestModel,
        variable=variable,
        models=model,
        file_type=file_type,
        start_hour=start_hour,
        end_hour=end_hour,
    )

    if not BASE_DIR.exists():
        logger.error("Forecast directory {} not availabale.".format(BASE_DIR))
        raise HTTPException(status_code=404, detail="Forecast not available")

    files = get_files_for_variable(
        request, variable, model, file_type, start_hour, end_hour
    )

    if not files:
        raise HTTPException(
            status_code=404,
            detail=f"No {file_type} files found for the given variable, model, and hour range",
        )

    # Set Cache-Control header for 10 minutes
    response.headers["Cache-Control"] = "public, max-age=600"

    return ForecastResponse(forecast=files)


@router.get("/files/velocity/{model}/{filename}")
async def get_leaflet_velocity_file(
    model: str, filename: str, request: Request, response: Response
):
    """
    Endpoint to download a gzipped velocity file.
    Clients must send 'Accept-Encoding: gzip' in the request headers.
    Careful, this wont work in swagger UI.
    """
    # Check if the client accepts gzip encoding
    accept_encoding = request.headers.get("Accept-Encoding", "")
    if "gzip" not in accept_encoding.lower():
        raise HTTPException(
            status_code=406,  # Not Acceptable
            detail="Client must accept gzip encoding. Send 'Accept-Encoding: gzip' header.",
        )

    file_path = safe_join(BASE_DIR, model, "velocity", filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Velocity file not found")

    # Set the correct headers for a gzipped JSON response
    response.headers["Cache-Control"] = "public, max-age=600"
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Type"] = "application/json"
    # response.headers["Content-Disposition"] = f"inline; filename={filename}"

    # Stream the file to avoid loading large files into memory
    with open(file_path, "rb") as f:
        gzipped_content = f.read()

    return Response(
        content=gzipped_content,
        media_type="application/json",
        headers=response.headers,
    )
