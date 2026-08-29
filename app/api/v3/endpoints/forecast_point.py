from fastapi import APIRouter, HTTPException, Query, Response

from app.api.v3.endpoints.forecast_model.model_aa import ModelAromeArctic
from app.utils.timeseries_formater import format_xarray_to_timeseries
from app.utils.error import handle_processing_error

from app.models.forecast import (
    AvailableModelsResponse,
    ForecastModelInfo,
    AvailableVariablesResponse,
    ForecastVariable,
)

from app.utils.cache import cache_response


from loguru import logger
from datetime import datetime

import numpy as np

router = APIRouter()


FORECAST_MODELS = {"aa": ModelAromeArctic}

# Kept under 1h (not exactly 60min) because THREDDS serves the AROME-Arctic
# "latest" file as a rolling dataset; a full hour risks matching a forecast
# step that has just rolled off the served file.
FORECAST_TIME_TOLERANCE = np.timedelta64(59, "m")


def _resolve_forecast_dataset(
    model: str,
    ftype: str,
    variables: list[str],
    lat: float,
    lon: float,
    time: str,
):
    """Look up the model, fetch the requested dataset, and validate its time.

    Shared by get_forecast_data and get_forecast_data_netcdf so both endpoints
    stay in sync on model lookup, error handling, and time tolerance.
    """
    if model not in FORECAST_MODELS:
        raise HTTPException(status_code=404, detail="Model not available")

    try:
        parsed_time = datetime.fromisoformat(time)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format")

    logger.debug(
        f"Received request for model '{model}', type '{ftype}', variables {variables}, at location ({lat}, {lon}) and time {parsed_time}"
    )

    if ftype not in ("surface", "profile"):
        raise HTTPException(status_code=400, detail="Invalid type specified")

    model_cls = FORECAST_MODELS[model](latitude=lat, longitude=lon, time=parsed_time)

    try:
        if ftype == "surface":
            ds = model_cls.get_surface(variable=variables)
        else:
            ds = model_cls.get_profile(variable=variables)
    except ValueError as ve:
        handle_processing_error(ve, status_code=400, details=str(ve))
    except Exception as e:
        handle_processing_error(
            e, status_code=500, details="Error fetching forecast data"
        )

    if abs(ds.time.values - np.datetime64(parsed_time)) > FORECAST_TIME_TOLERANCE:
        logger.warning(
            f"Requested time {parsed_time} is not available in the latest forecast. Closest available time is {ds.time.values}."
        )
        raise HTTPException(
            status_code=404,
            detail="The requested time is not available in the latest forecast.",
        )

    return ds, parsed_time


@router.get("/models/", response_model=AvailableModelsResponse)
@cache_response(ttl=600)  # Cache for 10 minutes
async def get_available_forecast_models() -> AvailableModelsResponse:
    """Endpoint to retrieve available forecast models."""
    models_info = [
        ForecastModelInfo(
            id=key,
            name=model_cls.name,
            provider=model_cls.provider,
            resolution=model_cls.resolution,
        )
        for key, model_cls in FORECAST_MODELS.items()
    ]
    return AvailableModelsResponse(models=models_info)


@router.get("/{model}/variables/", response_model=AvailableVariablesResponse)
@cache_response(ttl=600)  # Cache for 10 minutes
async def get_available_variables(
    model: str,
    ftype: str = Query(
        None,
        description="Type of forecast to retrieve: 'surface', 'profile', or None for all",
    ),
) -> AvailableVariablesResponse:
    """Endpoint to retrieve available variables for a specific forecast model."""
    if model not in FORECAST_MODELS:
        raise HTTPException(status_code=404, detail="Model not available")

    model_cls = FORECAST_MODELS[model]

    if ftype == "surface":
        variables = model_cls.variables_surface
        variable_list = [
            ForecastVariable(variable=var, type="surface", model=model)
            for var, var_type in variables.items()
        ]
    elif ftype == "profile":
        variables = model_cls.variables_profile
        variable_list = [
            ForecastVariable(variable=var, type="profile", model=model)
            for var, var_type in variables.items()
        ]
    elif ftype is None:
        variable_list = [
            ForecastVariable(variable=var, type="surface", model=model)
            for var, var_type in model_cls.variables_surface.items()
        ] + [
            ForecastVariable(variable=var, type="profile", model=model)
            for var, var_type in model_cls.variables_profile.items()
        ]

    else:
        raise HTTPException(status_code=400, detail="Invalid type specified")

    return AvailableVariablesResponse(variables=variable_list)


@router.get("/{model}/{ftype}")
@cache_response(ttl=600)  # Cache for 10 minutes
async def get_forecast_data(
    model: str,
    ftype: str,
    variables: list[str] = Query(..., description="Variables to retrieve"),
    lat: float = Query(..., description="Latitude of the location"),
    lon: float = Query(..., description="Longitude of the location"),
    time: str = Query(..., description="Time for the forecast data (ISO format)"),
) -> Response:
    """Endpoint to retrieve forecast data for a specific model, variable, and location."""
    ds, _ = _resolve_forecast_dataset(model, ftype, variables, lat, lon, time)

    stid = "forecast_{model}_{ftype}_{lat:.0f}_{lon:.0f}".format(
        model=model,
        ftype=ftype,
        lat=ds.latitude.values * 1e4,
        lon=ds.longitude.values * 1e4,
    )
    res = format_xarray_to_timeseries(ds, station_id=stid.replace(".", ""))

    logger.debug(f"Formatted forecast data: {res}")

    return res


@router.get("/{model}/{ftype}/nc")
@cache_response(ttl=600)  # Cache for 10 minutes
async def get_forecast_data_netcdf(
    model: str,
    ftype: str,
    variables: list[str] = Query(..., description="Variables to retrieve"),
    lat: float = Query(..., description="Latitude of the location"),
    lon: float = Query(..., description="Longitude of the location"),
    time: str = Query(..., description="Time for the forecast data (ISO format)"),
) -> Response:
    """Endpoint to retrieve forecast data for a specific model, variable, and location."""
    ds, parsed_time = _resolve_forecast_dataset(model, ftype, variables, lat, lon, time)

    stid = "forecast_{model}_{ftype}_{lat:.0f}_{lon:.0f}_{time}".format(
        model=model,
        ftype=ftype,
        lat=ds.latitude.values * 1e4,
        lon=ds.longitude.values * 1e4,
        time=parsed_time.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    nc_bytes = ds.to_netcdf(encoding={var: {"zlib": True} for var in ds.data_vars})
    return Response(
        content=nc_bytes,
        media_type="application/x-netcdf",
        headers={"Content-Disposition": f"attachment; filename={stid}.nc"},
    )
