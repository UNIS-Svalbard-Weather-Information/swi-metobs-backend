from fastapi import APIRouter
from app.api.v3.endpoints import forecast_rasters
from app.api.v3.endpoints import observation_historical
from app.api.v3.endpoints import observation_latest
from app.api.v3.endpoints import stations_informations
from app.api.v3.endpoints import spheres
from app.api.v3.endpoints import forecast_point

api_router = APIRouter()
api_router.include_router(
    forecast_rasters.router, prefix="/forecast", tags=["Weather Forecast Rasters"]
)

api_router.include_router(
    forecast_point.router,
    prefix="/point-forecast",
    tags=["Weather Forecast Point Data"],
)

api_router.include_router(
    stations_informations.router, prefix="/station-status", tags=["Station Status"]
)
api_router.include_router(
    observation_latest.router, prefix="/observations", tags=["Latest Observations"]
)
api_router.include_router(
    observation_historical.router,
    prefix="/historical",
    tags=["Historical Observations"],
)

api_router.include_router(
    spheres.router, prefix="/spheres", tags=["Birds eyes spheres"]
)
