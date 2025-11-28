from fastapi import APIRouter
from app.api.v3.endpoints import forecast

api_router = APIRouter()
api_router.include_router(forecast.router, prefix="/forecast", tags=["forecast"])
