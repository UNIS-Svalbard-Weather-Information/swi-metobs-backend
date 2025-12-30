from fastapi import APIRouter
from app.api.v3.endpoints import forecast
from app.api.v3.endpoints import stations_info
from app.api.v3.endpoints import obs_latest

api_router = APIRouter()
api_router.include_router(
    forecast.router, prefix="/forecast", tags=["Weather Forecast"]
)
api_router.include_router(
    stations_info.router, prefix="/station-status", tags=["Station Status"]
)
api_router.include_router(
    obs_latest.router, prefix="/observations", tags=["Latest Observations"]
)
