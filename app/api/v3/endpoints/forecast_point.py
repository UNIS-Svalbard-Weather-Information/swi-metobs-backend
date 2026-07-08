from fastapi import APIRouter, HTTPException, Query, Response

from app.api.v3.endpoints.forecast_model.model_aa import ModelAromeArctic
from app.utils.timeseries_formater import format_xarray_to_timeseries

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
    if model not in FORECAST_MODELS:
        raise HTTPException(status_code=404, detail="Model not available")

    time = datetime.fromisoformat(time)
    logger.debug(
        f"Received request for model '{model}', type '{ftype}', variables {variables}, at location ({lat}, {lon}) and time {time}"
    )

    model_cls = FORECAST_MODELS[model](latitude=lat, longitude=lon, time=time)

    try:
        if ftype == "surface":
            ds = model_cls.get_surface(variable=variables)
        elif ftype == "profile":
            ds = model_cls.get_profile(variable=variables)
        else:
            raise HTTPException(status_code=400, detail="Invalid type specified")
    except ValueError as ve:
        logger.error(f"Value error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error fetching forecast data: {e}")
        raise HTTPException(status_code=500, detail="Error fetching forecast data")

    if abs(ds.time.values - np.datetime64(time)) > np.timedelta64(59, "m"):
        logger.warning(
            f"Requested time {time} is not available in the latest forecast. Closest available time is {ds.time.values}."
        )
        raise HTTPException(
            status_code=404,
            detail="The requested time is not available in the latest forecast.",
        )

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
    if model not in FORECAST_MODELS:
        raise HTTPException(status_code=404, detail="Model not available")

    time = datetime.fromisoformat(time)
    logger.debug(
        f"Received request for model '{model}', type '{ftype}', variables {variables}, at location ({lat}, {lon}) and time {time}"
    )

    model_cls = FORECAST_MODELS[model](latitude=lat, longitude=lon, time=time)

    try:
        if ftype == "surface":
            ds = model_cls.get_surface(variable=variables)
        elif ftype == "profile":
            ds = model_cls.get_profile(variable=variables)
        else:
            raise HTTPException(status_code=400, detail="Invalid type specified")
    except ValueError as ve:
        logger.error(f"Value error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error fetching forecast data: {e}")
        raise HTTPException(status_code=500, detail="Error fetching forecast data")

    if abs(ds.time.values - np.datetime64(time)) > np.timedelta64(1, "h"):
        logger.warning(
            f"Requested time {time} is not available in the latest forecast. Closest available time is {ds.time.values}."
        )
        raise HTTPException(
            status_code=404,
            detail="The requested time is not available in the latest forecast.",
        )

    stid = "forecast_{model}_{ftype}_{lat:.0f}_{lon:.0f}_{time}".format(
        model=model,
        ftype=ftype,
        lat=ds.latitude.values * 1e4,
        lon=ds.longitude.values * 1e4,
        time=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    nc_bytes = ds.to_netcdf(encoding={var: {"zlib": True} for var in ds.data_vars})
    return Response(
        content=nc_bytes,
        media_type="application/x-netcdf",
        headers={"Content-Disposition": f"attachment; filename={stid}.nc"},
    )
